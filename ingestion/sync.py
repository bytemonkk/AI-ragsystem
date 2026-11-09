"""Batch ingest public JSONL; idempotent by URL + checksum.
Qdrant writes happen before the SQL commit; failure leaves a pending record for retry.
Never ingest private records into the public vector index.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urldefrag
from sqlalchemy import select, delete
from database.connection import SessionLocal
from database.models import SourceDocument, DocumentChunk
from retrieval.hybrid_retriever import index_document

def chunks_of(text: str, size: int = 1100, overlap: int = 140) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    if not text: return []
    result = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            split = text.rfind(' ', start + size // 2, end)
            if split > start: end = split
        result.append(text[start:end].strip())
        if end == len(text): break
        start = max(start + 1, end - overlap)
    return result

def ingest_record(item: dict) -> str:
    raw_url = item['url']
    url = urldefrag(raw_url)[0].rstrip('/') or raw_url
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname: raise ValueError('Document URL must be HTTPS')
    if item.get('access_level', 'public') != 'public': raise ValueError('Only public documents may be indexed')
    body = item['text'].strip()
    if not body: return 'empty'
    checksum = hashlib.sha256(body.encode()).hexdigest()
    doc_id = hashlib.sha256(url.encode()).hexdigest()
    with SessionLocal() as db:
        prior = db.get(SourceDocument, doc_id)
        if prior and prior.checksum == checksum and prior.status == 'indexed': return 'unchanged'
        doc = prior or SourceDocument(id=doc_id, url=url, title=item.get('title') or url, checksum=checksum)
        doc.title = item.get('title') or url
        doc.department = item.get('department') or None
        doc.category = item.get('category', 'general')
        doc.access_level = 'public'
        doc.checksum = checksum
        doc.status = 'pending'
        doc.updated_at = datetime.now(timezone.utc)
        db.add(doc)
        db.commit()
        segments = chunks_of(body)
        chunk_records = [(f'{doc_id}:{i}', part) for i, part in enumerate(segments)]
        try:
            index_document(doc, chunk_records)
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
            db.add_all([DocumentChunk(id=cid, document_id=doc_id, chunk_index=i, text=part)
                        for i, (cid, part) in enumerate(chunk_records)])
            doc.status = 'indexed'
            db.commit()
        except Exception:
            db.rollback()
            raise
    return 'indexed'

def run(path: str):
    summary = {'indexed': 0, 'unchanged': 0, 'empty': 0, 'failed': 0}
    with open(path, encoding='utf-8') as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip(): continue
            try: summary[ingest_record(json.loads(line))] += 1
            except Exception as exc:
                summary['failed'] += 1
                print(f'Failed at line {line_number}: {exc}')
    print(summary)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('jsonl')
    run(p.parse_args().jsonl)
