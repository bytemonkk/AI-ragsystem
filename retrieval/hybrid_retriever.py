"""Dense vector search + PostgreSQL FTS, merged with reciprocal-rank fusion.
BGE-M3 weights are created lazily; query and indexing always share one model.
"""
import uuid
from functools import lru_cache
from sqlalchemy import text as sqltext
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient, models
from database.config import settings
from database.models import SourceDocument

@lru_cache(maxsize=1)
def embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings().embed_model, device='cpu')

@lru_cache(maxsize=1)
def qdrant():
    return QdrantClient(url=settings().qdrant_url, timeout=30)

def ensure_collection():
    client = qdrant()
    name = settings().qdrant_collection
    if not client.collection_exists(name):
        client.create_collection(name, vectors_config=models.VectorParams(size=settings().embed_dim, distance=models.Distance.COSINE))

def embed(text: str) -> list[float]:
    return embedder().encode(text, normalize_embeddings=True).tolist()

def index_document(doc: SourceDocument, chunks: list[tuple[str, str]]):
    ensure_collection()
    # Remove prior chunks before replacement to prevent stale versions.
    qdrant().delete(collection_name=settings().qdrant_collection, points_selector=models.FilterSelector(
        filter=models.Filter(must=[models.FieldCondition(key='document_id', match=models.MatchValue(value=doc.id))])))
    for start in range(0, len(chunks), 32):
        batch = chunks[start:start + 32]
        points = [models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)),
            vector=embed(content), payload={'chunk_id': chunk_id, 'document_id': doc.id, 'text': content,
            'title': doc.title, 'url': doc.url, 'department': doc.department or '',
            'category': doc.category, 'access_level': doc.access_level}) for chunk_id, content in batch]
        qdrant().upsert(collection_name=settings().qdrant_collection, points=points, wait=True)

def search(db: Session, query: str, department: str | None = None, limit: int = 5) -> list[dict]:
    ensure_collection()
    filters = [models.FieldCondition(key='access_level', match=models.MatchValue(value='public'))]
    if department: filters.append(models.FieldCondition(key='department', match=models.MatchValue(value=department)))
    hits = qdrant().query_points(collection_name=settings().qdrant_collection, query=embed(query),
        query_filter=models.Filter(must=filters), limit=25, with_payload=True).points
    dense = [p.payload['chunk_id'] for p in hits]
    # Only public sources. Bound parameters prevent injection.
    statement = sqltext('''SELECT c.id FROM document_chunks c JOIN source_documents d ON d.id = c.document_id
        WHERE d.access_level = 'public' AND d.status = 'indexed'
        AND (
            CAST(:dept AS TEXT) IS NULL
            OR d.department = CAST(:dept AS TEXT)
        )
        AND to_tsvector('english', c.text) @@ websearch_to_tsquery('english', :query)
        ORDER BY ts_rank_cd(to_tsvector('english', c.text), websearch_to_tsquery('english', :query)) DESC LIMIT 25''')
    lexical = [row[0] for row in db.execute(statement, {'query': query, 'dept': department}).all()]
    scores: dict[str, float] = {}
    for ranking in (dense, lexical):
        for rank, chunk_id in enumerate(ranking): scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (60 + rank + 1)
    ranked = sorted(scores, key=scores.get, reverse=True)[:limit]
    if not ranked: return []
    from database.models import DocumentChunk
    records = {c.id: c for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(ranked)).all()}
    docs = {d.id: d for d in db.query(SourceDocument).filter(SourceDocument.id.in_([records[i].document_id for i in ranked if i in records])).all()}
    result = []
    for key in ranked:
        if key not in records: continue
        chunk = records[key]
        doc = docs.get(chunk.document_id)
        if not doc or doc.status != 'indexed' or doc.access_level != 'public': continue
        result.append({'text': chunk.text, 'source_url': doc.url, 'title': doc.title, 'score': round(scores[key], 5), 'chunk_id': key})
    return result
