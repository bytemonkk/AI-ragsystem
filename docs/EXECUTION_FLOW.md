# Execution flow and file responsibilities

## A. Startup sequence

1. `docker compose up -d --build` starts PostgreSQL (`postgres`), Qdrant (`qdrant`), FastAPI (`api`) and static developer frontend (`frontend`).
2. `api` runs `alembic upgrade head`. `database/migrations/versions/0001_initial.py` creates the structured tables and PostgreSQL GIN full-text index.
3. `api.main:app` registers routes under `/api/v1`. Dependency health is checked through `/health/ready`.
4. `retrieval.hybrid_retriever.embedder()` lazily loads `BAAI/bge-m3` only when an embedding is required. Model weights are cached in a Docker volume.
5. `retrieval.hybrid_retriever.ensure_collection()` creates the named Qdrant collection on first query/indexing request.

## B. Public document ingestion

`ingestion/crawler.py` -> `ingestion/parsers/html_parser.py` -> `data/crawl.jsonl` -> `ingestion/sync.py` -> `database/models.SourceDocument` (pending) -> `ingestion.sync.chunks_of` -> `retrieval/hybrid_retriever.index_document` -> Qdrant points -> `database/models.DocumentChunk` + `SourceDocument` (indexed).

- Every URL has a deterministic ID and content checksum. Unchanged indexed content is skipped.
- Source text and status live in PostgreSQL. The vector index is a derived search index.
- Vector index may temporarily contain an updated version when PostgreSQL commit fails; `SourceDocument.status` gates what gets returned. Re-run ingestion to reconcile. This is a recoverable but nontransactional two-store pipeline; production needs an outbox, reconciliation jobs, and metrics.
- Data is public-only. This pipeline does **not** crawl login-protected pages.
- PDF extraction is available in `ingestion/parsers/pdf_parser.py` but not automatically wired into the HTML crawler. Run a separate approved PDF import pipeline to add those documents.

## C. Faculty and timetable imports

`examples/faculty.csv` -> `scripts/import_structured.py faculty` -> PostgreSQL departments + faculty.

`examples/timetable.csv` -> `ingestion/parsers/timetable_parser.py` -> `scripts/import_structured.py timetable` -> PostgreSQL subjects + sections + rooms + timetable_entries.

Faculty photos are official URLs, not image embeddings. Import only verified records. A PDF table is NOT automatically assumed correct.

## D. API query execution

### Faculty profile and image

`POST /api/v1/chat` -> `api/routes/chat.py` -> `retrieval/query_router.answer` -> `retrieval/entity_resolver.classify` -> `services/faculty_service.find_faculty` -> PostgreSQL -> name/designation/image_url/profile_url JSON -> `frontend/index.html` renders the card.

`GET /api/v1/faculty/search?q=...&department=CSE` and `GET /api/v1/faculty/{id}` do direct structured lookups.

### "What period do I have now?"

`POST /api/v1/auth/login` -> JWT bearer -> `POST /api/v1/chat` (or `GET /api/v1/timetable/me/current-class`) -> `api/auth/security.current_user` -> account faculty_id -> `services/timetable_service.schedule` -> current **Asia/Kolkata** day/time -> PostgreSQL timetable + cancellation/holiday exceptions -> JSON period card. No LLM and no vector lookup are required.

When today's schedule contains a holiday or cancellation, the result reflects known exceptions. Unrecorded last-minute changes cannot be inferred.

### Document questions

`POST /api/v1/chat` -> `retrieval/query_router.answer` -> `retrieval/hybrid_retriever.search` -> Qdrant dense top 25 + Postgres full-text top 25 -> reciprocal rank fusion -> public/indexed source verification -> `generator/generator.generate_answer` -> evidence and URLs.

An optional OpenAI-compatible LLM produces a source-grounded answer. If unconfigured, the API returns top evidence text, not an invented summary.

## E. Example trace

Question: **"Who is the CSE HoD?"**

1. `entity_resolver.classify` returns `faculty`.
2. `extract_department` returns `CSE`.
3. `faculty_service.find_faculty` runs a PostgreSQL query for active HoD in CSE.
4. The API returns matching faculty rows. A faculty photograph appears only when a trusted `image_url` was imported.

Question: **"What period do I have now?"**

1. `entity_resolver.classify` returns `personal_timetable`.
2. Anonymous users are asked to sign in.
3. The verified user’s faculty ID selects the appropriate timetable.
4. The current local clock is compared against `start_time <= now < end_time`.
5. The API returns matching subject, section, room, branch and source.

Question: **"Explain the attendance requirements"**

1. Classified as `documents`.
2. Qdrant semantic search and PostgreSQL lexical search run.
3. Results are fused, filtered to indexed public sources, and formatted with URLs.
4. The LLM answers only when configured and evidence is available.

## F. Known gaps before real campus production

1. Timetable PDF layouts, row-spanning lab periods, multi-instructor classes and reschedules need CBIT-specific extractors and validation.
2. `faculty` entity resolution is simple rule-based matching, not a complete coreference/conversation-memory system ("show her" alone is not yet resolved across requests).
3. Source freshness is checksum-based on manually rerun ingestion; scheduled delta crawling, deleted page detection, official publication dates and version priority are future work.
4. Institution-wide login requires OIDC/SSO + role/department synchronization and additional authorization checks; the bootstrap password workflow is for development only.
5. Qdrant and PostgreSQL updates are non-atomic and require a job queue/outbox plus reconciliation for reliable large-scale ingestion.
6. Photo hosting currently uses original public image URLs; object-storage mirroring, media security and multimodal image embeddings are not present.
7. Retrieval evaluation, RAG prompt-injection testing, real observability, load tests and deployment operations remain before production launch.
8. Only current weekday and current period are supported. Holidays and cancellations must be imported into `schedule_exceptions` by authorized administrators.
9. `faculty_id` and timetable data must be imported and identity-matched; 250 MB of downloaded data is not available inside this package.
10. No institutional production deployment should be performed without privacy, security, and access reviews.
