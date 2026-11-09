# CBIT RAG Assistant v2

A Docker-based **college information assistant prototype** for the public [Chaitanya Bharathi Institute of Technology (CBIT)](https://www.cbit.ac.in/) website. It combines **PostgreSQL**, **Qdrant**, **BGE-M3 embeddings**, **FastAPI**, and a lightweight frontend to retrieve CBIT webpages and documents. It also supports curated faculty profiles and authenticated faculty timetable lookups.

> **Project status — tested development checkpoint (November 2026).** This repository is **not** a production-ready campus service and does **not** automatically cover the entire CBIT website yet. The steps below document the capabilities verified during development and identify work still pending.
>
> This README documents the local changes made during testing, including `ingestion/parsers/homepage_parser.py`, the enhanced `ingestion/parsers/html_parser.py`, OCR-enabled `ingestion/parsers/pdf_parser.py`, `ingestion/pdf_ingestor.py`, the improved `ingestion/crawler.py`, and the updated `retrieval/entity_resolver.py`. **Make sure these files are saved in your checkout before committing.** They were added/edited after the original v2 archive was created.

## Contents

- [1. What works today](#1-what-works-today)
- [2. System architecture](#2-system-architecture)
- [3. Requirements](#3-requirements)
- [4. Get the code and configure secrets](#4-get-the-code-and-configure-secrets)
- [5. Start Docker](#5-start-docker)
- [6. Load sample data](#6-load-sample-data)
- [7. Crawl CBIT HTML pages](#7-crawl-cbit-html-pages)
- [8. Download and extract linked PDFs](#8-download-and-extract-linked-pdfs)
- [9. Index documents](#9-index-documents)
- [10. Test the API](#10-test-the-api)
- [11. Faculty timetable testing](#11-faculty-timetable-testing)
- [12. Execution flow and module map](#12-execution-flow-and-module-map)
- [13. Troubleshooting](#13-troubleshooting)
- [14. Known limitations and roadmap](#14-known-limitations-and-roadmap)
- [15. GitHub and security checklist](#15-github-and-security-checklist)

## 1. What works today

| Capability | Current state |
| --- | --- |
| Docker Compose: PostgreSQL, Qdrant, API, frontend | Tested locally |
| SQL migrations on API startup | Tested locally |
| Import curated faculty and timetable CSVs | Tested with sample records |
| Query intent routing (`documents`, `faculty`, `personal_timetable`) | Basic rule-based implementation tested |
| HTML crawler with URL normalization, robots.txt, delays | Tested on 10 public CBIT pages |
| Specialized homepage cleanup and general HTML parsing | Tested on representative pages |
| PDF link discovery from one HTML page | Tested |
| PDF download + PyMuPDF extraction + Tesseract fallback | Tested on 3 real CBIT PDFs (4 OCR pages) |
| BGE-M3 dense indexing in Qdrant | Tested |
| PostgreSQL full-text search + Qdrant Reciprocal Rank Fusion | Functional; ranking still needs improvement |
| Chat endpoint returns sourced evidence | Tested |
| Optional OpenAI-compatible LLM synthesis | Code path present; not configured/tested in this checkpoint |
| Entire-site PDF/image crawling and incremental scheduled sync | **Not implemented** |
| Automatic extraction of faculty profiles, photos and timetables from every CBIT page | **Not implemented** |
| Campus SSO / public production deployment | **Not implemented** |

In the documented local test, **10 HTML pages** were refreshed successfully, **3 PDF documents** were indexed, and a parent–teacher meeting PDF appeared in search results. It ranked **second** behind the homepage, so retrieval quality is still being improved.

## 2. System architecture

```text
                          User / Developer UI (:8080)
                                      |
                            FastAPI (:8000)
                                      |
                       query_router / intent classifier
                          /          |            \
                         /           |             \
                   Faculty lookup  Timetable lookup   Document lookup
                       |             |                 |
                       +-------------+         +-------+-------+
                       |                       |               |
                 PostgreSQL (:5432)     PostgreSQL FTS    Qdrant (:6333)
                 structured records      keyword search   BGE-M3 vectors
                                                 \          /
                                                  RRF fusion
                                                      |
                                                 evidence + URLs
                                                      |
                                         Optional configured LLM

  Public CBIT website
       |
       +-- ingestion/crawler.py --------> HTML JSONL ---------+
       |                                                     |
       +-- ingestion/pdf_ingestor.py ---> PDF/OCR JSONL -----+--> ingestion/sync.py
                                                                    |
                                                        PostgreSQL + Qdrant
```

**Why multiple stores?** PostgreSQL holds faculty, departments, room/timetable entities, document registry and chunk text. Qdrant stores dense vector representations for semantic search. PDFs and images do not belong exclusively in a vector database. A production media/object store is still future work; profile photos currently use official HTTPS image URLs where provided in curated records.

## 3. Requirements

- Docker Desktop (Windows + WSL2), or Docker Engine with Docker Compose on Linux/macOS.
- Git and a terminal (examples primarily use **Windows PowerShell**).
- Internet access to pull Docker images, download the **BAAI/bge-m3** model, and crawl permitted public pages.
- Several GB of disk space and adequate RAM. The BGE-M3 model is large; CPU embedding may be slow on a laptop with ~7–8 GiB Docker memory.
- Authorized, responsible crawling: respect `robots.txt`, use a real contact in the crawler user-agent, and avoid overwhelming CBIT's site. Only ingest public information; internal/student-specific information requires authorization.

Ports are exposed **only on localhost** by the supplied `docker-compose.yml`:

| Service | Local address |
| --- | --- |
| Developer frontend | http://localhost:8080 |
| Swagger API docs | http://localhost:8000/docs |
| API readiness | http://localhost:8000/health/ready |
| Qdrant dashboard | http://localhost:6333/dashboard |
| PostgreSQL | localhost:5432 |

## 4. Get the code and configure secrets

If cloning this repo for the first time:

```powershell
git clone https://github.com/bytemonkk/cbit-rag-assistant.git
cd cbit-rag-assistant
```

If your v2 project is in a separate folder, open **that folder** instead; all following commands must run from the directory containing `docker-compose.yml`.

Copy the configuration:

```powershell
Copy-Item .env.example .env
notepad .env
```

Configure these values in `.env`:

```dotenv
# Example local-only values — replace passwords/secrets before real usage
DATABASE_URL=postgresql+psycopg://cbit:CHANGE_ME@postgres:5432/cbit
POSTGRES_DB=cbit
POSTGRES_USER=cbit
POSTGRES_PASSWORD=CHANGE_ME
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=cbit_documents_v2
EMBED_MODEL=BAAI/bge-m3
EMBED_DIM=1024
JWT_SECRET=REPLACE_WITH_STRONG_RANDOM_SECRET
JWT_ALGORITHM=HS256
ADMIN_BOOTSTRAP_EMAIL=admin@example.invalid
ADMIN_BOOTSTRAP_PASSWORD=REPLACE_WITH_STRONG_ADMIN_PASSWORD
CORS_ORIGINS=http://localhost:8080
ALLOWED_CRAWL_HOSTS=www.cbit.ac.in,cbit.ac.in
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

Use the actual `.env.example` from your checkout as the authoritative list of variables. **`DATABASE_URL` password must match `POSTGRES_PASSWORD` for a fresh database.** If the PostgreSQL volume already exists, changing the password in `.env` does not automatically change the password of the existing database user.

Generate strong secrets with **Windows PowerShell 5.1-compatible** code (writes to `.env` directly, prints no secrets):

```powershell
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$jwtBytes = New-Object byte[] 48
$adminBytes = New-Object byte[] 24
$rng.GetBytes($jwtBytes)
$rng.GetBytes($adminBytes)
$rng.Dispose()
$jwt = [Convert]::ToBase64String($jwtBytes)
$admin = [Convert]::ToBase64String($adminBytes)
$envPath = Join-Path (Get-Location) '.env'
$content = [System.IO.File]::ReadAllText($envPath)
$content = $content.Replace('REPLACE_WITH_A_LONG_RANDOM_SECRET_AT_LEAST_32_CHARACTERS', $jwt)
$content = $content.Replace('REPLACE_WITH_A_STRONG_BOOTSTRAP_PASSWORD', $admin)
[System.IO.File]::WriteAllText($envPath, $content)
Write-Host 'JWT/admin placeholders processed; verify .env locally without sharing it.'
```

The replacement only affects those **exact placeholder strings**. If you changed them, manually set the values instead. Never paste `.env`, passwords, JWT tokens, or API keys into issues, screenshots, or commits.

**Optional LLM:** You can leave `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` empty. Retrieval still works, but the API returns indexed passages instead of natural-language LLM synthesis.

## 5. Start Docker

```powershell
docker --version
docker compose version
docker compose config --quiet
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health/ready
```

Expected readiness result: `status: ready`. The API container executes Alembic migrations before starting Uvicorn.

Useful commands:

```powershell
docker compose logs --tail=100 api
docker compose logs -f api
docker compose restart api
docker compose down                 # stops containers; preserves volumes
# NEVER run 'docker compose down -v' unless you deliberately want to delete volumes
```

Editing Python source requires rebuilding the API container with the supplied Dockerfile (`COPY . .`):

```powershell
docker compose up -d --build api
```

## 6. Load sample data

The files in `examples/` are **illustrative**—not authoritative CBIT faculty or schedule data.

```powershell
docker compose exec api python -m scripts.bootstrap_admin
docker compose exec api python -m scripts.import_structured faculty examples/faculty.csv
docker compose exec api python -m scripts.import_structured timetable examples/timetable.csv
docker compose exec api python -m ingestion.sync examples/documents.jsonl
```

Check SQL counts without opening the psql pager:

```powershell
docker compose exec postgres psql -P pager=off -U cbit -d cbit -c "SELECT COUNT(*) FROM faculty;"
docker compose exec postgres psql -P pager=off -U cbit -d cbit -c "SELECT COUNT(*) FROM timetable_entries;"
docker compose exec postgres psql -P pager=off -U cbit -d cbit -c "SELECT COUNT(*) FROM source_documents;"
```

The **first** embedding operation downloads BGE-M3. It will not require an `HF_TOKEN` for public access, though an optional token can improve Hub download limits. Do not add tokens to committed files.

## 7. Crawl CBIT HTML pages

> Ensure your modified `ingestion/crawler.py`, `homepage_parser.py`, and `html_parser.py` are present. Set a real contact address in `USER_AGENT`, verify permitted access, and keep a conservative request delay.

Start with a **small test**:

```powershell
docker compose exec api python -m ingestion.crawler --start https://www.cbit.ac.in/ --output data/cbit_html_test.jsonl --max-pages 10 --delay 1.5
```

View a compact extraction summary without printing the full data:

```powershell
@'
import json
from pathlib import Path
p = Path('data/cbit_html_test.jsonl')
rows = [json.loads(line) for line in p.open(encoding='utf-8') if line.strip()]
print('Records:', len(rows))
for row in rows:
    print(row['title'], '|', row['url'], '| characters:', len(row['text']))
'@ | docker compose exec -T api python -
```

The crawler uses HTTPS, a host allowlist, URL normalization, robots checks and controlled delays. It **currently extracts HTML text only** and is not a complete website inventory. It does not automatically download all linked PDFs, images, office files, or authenticated content. Don't increase the limit dramatically until extraction quality and crawl policy have been reviewed.

## 8. Download and extract linked PDFs

The updated Dockerfile must install `tesseract-ocr` and `tesseract-ocr-eng` for scanned-PDF OCR. Confirm availability:

```powershell
docker compose exec api tesseract --version
```

Download a small batch of PDFs linked directly from the homepage:

```powershell
docker compose exec api python -m ingestion.pdf_ingestor --page https://www.cbit.ac.in/ --output data/cbit_pdf_test.jsonl --max-pdfs 3
```

The separate `pdf_ingestor.py` checks approved HTTPS hosts and robots policy, limits downloads to 25 MiB, rejects unexpected redirects, invokes `parse_pdf()`, and writes public JSONL records. The PDF parser tries PyMuPDF text extraction first and Tesseract OCR for pages with insufficient extracted text.

Review extraction before indexing—especially **fees, dates, attendance requirements and timetable tables**:

```powershell
@'
import json
from pathlib import Path
p = Path('data/cbit_pdf_test.jsonl')
rows = [json.loads(line) for line in p.open(encoding='utf-8') if line.strip()]
print('PDF records:', len(rows))
for row in rows:
    print('\nTITLE:', row['title'])
    print('URL:', row['url'])
    print('CHARS:', len(row['text']))
    print('PREVIEW:', row['text'][:800])
'@ | docker compose exec -T api python -
```

OCR is **fallible**. Successful extraction is not proof that amounts, percentages, dates, names, or tables are correct. Do not automatically convert OCR timetable output into authoritative faculty schedules without review.

## 9. Index documents

Once you have inspected the JSONL output:

```powershell
docker compose exec api python -m ingestion.sync data/cbit_html_test.jsonl
docker compose exec api python -m ingestion.sync data/cbit_pdf_test.jsonl
```

Typical output:

```text
{'indexed': 3, 'unchanged': 0, 'empty': 0, 'failed': 0}
```

`ingestion/sync.py` normalizes trailing slashes, computes a SHA-256 document ID from the normalized URL and a content checksum, writes public document/chunk metadata to PostgreSQL, and calls `index_document()` to update Qdrant points. Unchanged indexed records are skipped. **This process is not yet crash-safe across PostgreSQL and Qdrant:** unexpected failures between stores require reconciliation/retry. Old Qdrant points are deleted before replacement; do not run continuous unattended synchronization until versioned or recoverable indexing has been implemented.

Verify Qdrant:

```powershell
Invoke-RestMethod http://localhost:6333/collections/cbit_documents_v2 | ConvertTo-Json -Depth 8
```

A `green` collection with positive `points_count` confirms points exist. For tiny collections, `indexed_vectors_count: 0` can be normal.

## 10. Test the API

Open **http://localhost:8000/docs** or **http://localhost:8080**.

PowerShell example:

```powershell
$body = @{ question = 'When is the CBIT B.E/B.Tech first semester parent teacher meeting scheduled in November 2026?' } | ConvertTo-Json
$response = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/chat' -Method Post -ContentType 'application/json' -Body $body
$response.intent
$response.answer
$response.evidence | Select-Object title, source_url, score
```

For that test, the expected **intent** is `documents`. A November 2026 local test retrieved the [Parent–Teacher Meeting PDF](https://www.cbit.ac.in/wp-content/uploads/2021/04/Parent-Teacher-meeting-schedule-on-07-11-2026-I-Sem-2026-27.docx.pdf), stating **7 November 2026 at 9:30 AM**. The PDF ranked second behind the homepage; improvement is pending. A source URL in a result does not itself prove every OCR-derived detail has been manually verified.

Other routes:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | DB and Qdrant readiness |
| POST | `/api/v1/chat` | Route chat questions |
| GET | `/api/v1/faculty/search?department=CSE` | Search curated faculty |
| POST | `/api/v1/auth/login` | Obtain JWT |
| GET | `/api/v1/auth/me` | Authenticated account |
| GET | `/api/v1/timetable/me` | Today's schedule for linked faculty |
| GET | `/api/v1/timetable/me/current-class` | Current scheduled period for linked faculty |

The current query router is **rule-based**, not an LLM agent. Meeting/circular/exam questions route to documents; HoD/photo questions route to faculty; personal period questions require a linked faculty account.

## 11. Faculty timetable testing

Bootstrap an administrator from `.env`:

```powershell
docker compose exec api python -m scripts.bootstrap_admin
```

To create a *development-only* faculty account linked to an imported faculty `external_id`:

```powershell
# Replace the sample ID/email and use a real secure value locally.
docker compose exec -e CBIT_USER_PASSWORD='CHANGE_ME_TO_A_LONG_TEST_PASSWORD' api python -m scripts.create_faculty_user faculty.demo@example.invalid DEMO001
```

In PowerShell, log in without pasting the token publicly:

```powershell
$creds = @{ email='faculty.demo@example.invalid'; password='CHANGE_ME_TO_A_LONG_TEST_PASSWORD' } | ConvertTo-Json
$login = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/auth/login' -Method Post -ContentType 'application/json' -Body $creds
$token = $login.access_token
Invoke-RestMethod 'http://localhost:8000/api/v1/timetable/me' -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod 'http://localhost:8000/api/v1/timetable/me/current-class' -Headers @{ Authorization = "Bearer $token" }
```

The demo timetable has a Monday period (09:00–10:00). An empty current-class response outside that period is expected. Real faculty timetable queries depend on **reviewed, currently valid CSV imports** and authenticated identity; they're not dynamically scraped from PDFs yet. Timezone used: **Asia/Kolkata**.

## 12. Execution flow and module map

```text
1. docker compose up -d --build
   └── postgres and qdrant containers start
   └── api executes alembic upgrade head → uvicorn api.main:app
   └── frontend served by nginx

2. ingestion/crawler.py → ingestion/parsers/{html_parser,homepage_parser}.py
   └── writes data/*.jsonl (public HTML)

3. ingestion/pdf_ingestor.py → ingestion/parsers/pdf_parser.py
   └── PyMuPDF text extraction; Tesseract OCR fallback
   └── writes data/*.jsonl (public PDFs)

4. ingestion/sync.py → retrieval/hybrid_retriever.index_document()
   └── PostgreSQL document registry/chunk text
   └── Qdrant document embeddings

5. POST /api/v1/chat → retrieval/query_router.py
   ├── faculty: services/faculty_service.py → PostgreSQL
   ├── personal_timetable: services/timetable_service.py → PostgreSQL
   └── documents: retrieval/hybrid_retriever.py
       ├── Qdrant dense vector search
       ├── PostgreSQL full-text search
       └── Reciprocal Rank Fusion → generator/generator.py
```

Primary folders:

```text
api/                 FastAPI routes and authentication
 database/           Settings, connection, ORM models, Alembic migrations
 ingestion/          HTML crawler, PDF ingestor, parsers, incremental batch sync
 retrieval/          Intent classification, hybrid retrieval, query router
 services/           Faculty and timetable domain logic
 generator/          Evidence fallback and optional LLM completion
 frontend/           Minimal browser UI
 scripts/            Admin bootstrap and curated CSV import tools
 examples/           Safe illustrative fixtures
 tests/              Basic automated tests
 docs/               Additional execution-flow notes
```

## 13. Troubleshooting

**`no such service: build`** — use `docker compose up -d --build` (two hyphens before `build`).

**500 / `psycopg.errors.AmbiguousParameter`** — older `hybrid_retriever.py` used `:dept IS NULL`; use `CAST(:dept AS TEXT) IS NULL` in the SQL condition (the tested checkout includes this fix).

**Wrong intent (`parent teacher meeting` → `faculty`)** — use the revised `retrieval/entity_resolver.py` that prioritizes meeting/circular/document vocabulary before generic `teacher` detection.

**`ScannedPDFError`** — some PDFs are image-based. Build the OCR-enabled image and verify Tesseract: `docker compose exec api tesseract --version`. Then use the OCR-enabled `pdf_parser.py`.

**Qdrant compatibility warning** — in the tested environment, `qdrant-client==1.20.0` communicated with `qdrant/qdrant:v1.12.6` but emitted a compatibility warning. **This remains unresolved.** Align supported server/client versions in a separate tested change and back up the persistent Qdrant volume before upgrading; don't simply suppress the warning.

**Lexical retrieval returns no matches for a long question** — `websearch_to_tsquery()` can be overly restrictive. During testing, `parent teacher meeting` matched the correct PDF, while a longer natural-language question did not. Planned fix: derive a concise keyword query separately from the dense semantic query and rerank results.

**Homepage outranks the PDF** — dense BGE-M3 retrieval currently favors an announcement snippet over the original circular. Planned fix: document-title/source-aware reranking, diversity, and evaluation; don't artificially force all PDFs above every page.

**Large build or RAM pressure** — BGE-M3 downloads substantial weights; keep Docker disk space free. The Dockerfile `pip install` layer may be rebuilt when OS package instructions change.

**No generated answer** — no LLM endpoint is set; the API returns retrieved passages by design.

**PowerShell `RandomNumberGenerator.Fill()` missing** — older Windows PowerShell/.NET versions support `RandomNumberGenerator.Create().GetBytes()`.

## 14. Known limitations and roadmap

1. Improve lexical query preprocessing and cross-encoder reranking; evaluate top-1 source accuracy on real CBIT questions.
2. Implement **recoverable/versioned synchronization** to avoid half-completed PostgreSQL/Qdrant updates and support old-document deletion.
3. Align Qdrant server/client versions and pin tested Python dependency versions.
4. Crawl all permitted, relevant CBIT sections (not just the homepage); discover linked PDFs, embedded PDF shortcodes, and documents across pages, with deduplication and politeness controls.
5. Preserve document-to-page links, publication/effective dates, section/department metadata, checksums and OCR-quality flags; review critical OCR values.
6. Build structured faculty-photo/profile extraction and verified timetable extraction for each published layout; implement schedule revisions and holidays.
7. Add security and operational controls: SSO/OIDC, role-based access, TLS, rate limiting, secret management, backups, job monitoring, and privacy checks.
8. Add regression tests for ingestion, retrieval quality, access control, OCR and schema migrations.

**Not supported yet:** a guaranteed complete index of the entire CBIT website, image-vector similarity search, private ERP access, real-time timetable edits or an institution-approved deployment.

## 15. GitHub and security checklist

The repository should track **source code, migrations, docs, examples and `.env.example`**—not `.env`, local datasets, Hugging Face model weights, cached files, raw PDF downloads, databases or JWT credentials. Use the accompanying `.gitignore` and review staged files **before every push**.

```powershell
# From the project root
git status
git remote -v
git branch --show-current

# After copying the replacement README.md and .gitignore into your checkout:
git add README.md .gitignore .env.example Dockerfile docker-compose.yml requirements.txt alembic.ini
git add api database ingestion retrieval services generator scripts frontend examples tests docs

git diff --cached --stat
git status --short
# Inspect the staged content and ensure no secrets or sensitive data are included.
git diff --cached --check

git commit -m "docs: checkpoint CBIT RAG v2 crawling OCR and hybrid retrieval"
# Only after confirming the branch and remote are correct:
git push -u origin HEAD
```

If `git remote -v` shows no remote, or you're working in a new standalone ZIP extraction, first decide whether to merge the v2 code into the existing GitHub repository or publish to a separate branch. **Do not force-push over the original prototype.** For a safe integration branch use `git switch -c feature/cbit-rag-v2` before committing.

A `.gitignore` prevents *new* files from being added; it **does not remove secrets already tracked**. If `.env` was ever committed, untrack it with `git rm --cached .env`, rotate exposed credentials, and consider Git-history remediation where appropriate.

---

**Disclaimer:** Unofficial development project; CBIT content belongs to its respective owners. Respect site access policies and source attribution. This documentation reflects tested prototype behavior, not institutional certification.
