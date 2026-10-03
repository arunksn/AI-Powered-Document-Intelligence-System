# Ledgerline — Document Intelligence Platform

Ledgerline is a production-oriented web application for intelligent document
processing and contract intelligence. Users create projects, upload PDF, DOCX,
XLSX, JPG, or PNG documents, and watch a CPU-bound pipeline process them in
real time. The pipeline preserves document structure, performs OCR when needed,
classifies document types, extracts entities and named clauses, detects anomalies,
computes risk, checks contradictions across related documents, and syncs a
structured record to Notion or Airtable.

## Architecture

```
                    ┌─────────────┐        ┌──────────────┐
   Browser  ───────▶│   FastAPI   │───────▶│  Postgres /  │
  (React/Vite)       │   (web)     │        │   SQLite     │
       ▲             └──────┬──────┘        └──────────────┘
       │ WebSocket           │ enqueue
       │ (live stage         ▼
       │  updates)     ┌─────────────┐
       └───Redis───────│   Celery    │
        pub/sub         │   worker    │
                        └──────┬──────┘
                               │
                    ┌──────────┴───────────┐
                    │  6-stage pipeline     │
                    │  0 Ingestion/OCR      │
                    │  1 Classification     │
                    │  2 Extraction         │
                    │  3 Anomaly detection  │
                    │  4 Risk scoring       │
                    │  5 Contradictions*    │
                    └──────────┬───────────┘
                               ▼
                        Notion / Airtable
```
\* Stage 5 runs at the **project** level once ≥2 documents are complete,
triggered as a follow-up task after each document finishes.

**Why Celery + Redis, not just async FastAPI handlers:** the pipeline
stages are CPU-bound (OCR, NER, regex extraction over large documents),
which would block FastAPI's event loop and stall every other request/
WebSocket on the same process. Offloading to Celery workers keeps the web
process responsive purely for HTTP + WebSocket I/O.

**Why Redis pub/sub between the worker and the browser:** the Celery
worker and the FastAPI process are separate OS processes (and on Railway,
potentially separate services). The worker can't call a function on the
web process directly, so it publishes a small JSON message per stage
transition to a Redis channel (`doc:{document_id}`); the web process,
subscribed to that channel for any document with an open WebSocket,
forwards the message straight to the browser. This is what makes stage
results appear "live" rather than as a single dump at the end.

## Memory management strategy (Railway free tier constraint)

Railway's free tier gives each service roughly 512MB–1GB of RAM. OCR
(Tesseract), NER (spaCy), and document parsing (PyMuPDF/python-docx/
openpyxl) can't all sit loaded in the same process at once without
risking an OOM kill — especially with more than one document processing
concurrently.

Implemented in `backend/app/pipeline/model_manager.py`:

- **Lazy loading** — no model loads at process startup. The spaCy NER
  model loads on first actual use (Stage 1 party/date extraction), so a
  worker that never reaches that stage never pays the load cost.
- **Model cycling** — `MAX_CONCURRENT_MODELS` (default `1`) caps how many
  heavyweight models are resident at once. Requesting a new model evicts
  the current one first rather than stacking memory usage.
- **Idle unload** — a background watchdog thread unloads a model after
  `MODEL_IDLE_UNLOAD_SECONDS` (default 120s) of no use, so memory is
  reclaimed between documents without pipeline code needing to manage it
  explicitly.
- **Tesseract runs as an external OS process** (via `pytesseract`), not a
  Python-resident model — it's spawned per page and exits when done, so
  it doesn't count against the in-process model budget at all.
- **Regex/rule-based extraction over a second NER model for clause
  values** — Stage 2 deliberately uses targeted regex (payment-term days,
  liability amounts, invoice line items) instead of a second transformer
  model, since clause *values* are highly structured and a second
  resident model would blow the memory budget for marginal accuracy gain.

Net effect: steady-state memory stays bounded to "one small model +
FastAPI/Celery overhead" regardless of how many documents have been
processed in the container's lifetime.

**Storage note:** Railway's free tier filesystem is ephemeral. Uploaded
originals live only in `UPLOAD_DIR` (`/tmp` by default) long enough for
the pipeline to run; the extracted structured data — the part that
matters — is persisted to Postgres/SQLite. If a document needs
reprocessing after a container restart, it must be re-uploaded (the UI
surfaces this with a clear error rather than failing silently).

## Repo layout

```
backend/
  app/
    main.py              FastAPI app + WebSocket endpoint
    celery_app.py         Celery config
    tasks.py               Pipeline orchestration (chains all 5 stages)
    models.py, schemas.py  DB models / API schemas
    websocket_manager.py   Redis <-> WebSocket bridge
    pipeline/
      model_manager.py     Lazy-load / idle-unload model registry
      ingestion.py          Section 1: format detection + normalisation
      ocr.py                 OCR + artefact correction + confidence flag
      classification.py     Stage 1
      extraction.py           Stage 2 (branches by document type)
      anomaly_detection.py   Stage 3
      risk_scoring.py         Stage 4
      contradiction_detection.py  Stage 5
      crm_sync.py              Section 3: Notion/Airtable upsert
    routers/
      projects.py, documents.py
  requirements.txt, Dockerfile, Procfile
frontend/
  src/
    pages/     ProjectsView, ProjectDetail, DocumentProcessing, DocumentDetail
    components/ StageCard, SeverityBadge, RiskChart, ContradictionCard, CrmSyncPanel
docker-compose.yml   local dev: postgres + redis + web + worker + frontend
```

## Local development

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/health
- The first `docker compose up` will download the spaCy `en_core_web_sm`
  model during the backend image build (a few hundred MB) — expect the
  first build to take a couple of minutes.

Without Docker:

```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
# needs Redis + Postgres (or leave DATABASE_URL as sqlite) running locally
uvicorn app.main:app --reload &
celery -A app.celery_app.celery_app worker --loglevel=info &

# frontend
cd frontend
npm install
npm run dev
```

## Deploying to Railway

This repo deploys as **three Railway services** from the same GitHub repo:

1. **web** — `backend/`, start command from `Procfile`'s `web:` line.
   Attach Railway's Postgres and Redis plugins; Railway injects
   `DATABASE_URL` and you set `REDIS_URL` from the Redis plugin's
   connection string.
2. **worker** — same `backend/` source, override the start command to
   the `Procfile`'s `worker:` line (Railway lets you set a custom start
   command per service from the same repo/root).
3. **frontend** — `frontend/`, build with `npm run build`, serve `dist/`
   with a static file server (e.g. `npx serve -s dist -l $PORT`). Set
   `VITE_API_URL` / `VITE_WS_URL` to the deployed **web** service's public
   URL (use `wss://` for the WebSocket URL once Railway terminates TLS).

For the Railway free-tier worker, keep `CELERY_CONCURRENCY=1` so the
model-memory budget applies to one active CPU inference process at a time.

Set `NOTION_API_KEY` + `NOTION_DATABASE_ID` (or the Airtable equivalents)
as environment variables on the **web** and **worker** services — CRM
sync runs from the worker, and manual retries are triggered from the web
API.

Set `PUBLIC_APP_URL` to the deployed frontend origin so CRM records contain a
real clickable link back to the document detail page. The Notion database (or Airtable table) needs these properties/fields:
`Name` (title/text), `ContentHash` (text), `DocumentType` (select/text),
`Project` (text), `PrimaryParties` (text), `RiskScore` (number),
`CriticalAnomalies` / `WarningAnomalies` / `InfoAnomalies` (number),
`PlatformLink` (url/text).

## Authentication

Signup/login is JWT-based (`backend/app/auth.py`): bcrypt-hashed
passwords, a single long-lived access token (7 days by default) issued at
signup/login, sent as `Authorization: Bearer <token>` on every request.
Projects belong to a user (`Project.owner_id`); every project/document
route checks ownership and returns a plain 404 (not 403) for another
user's resources, so a guessed ID can't be used to confirm something
exists.

The WebSocket endpoint can't receive an `Authorization` header (browsers
don't support custom headers on the WS handshake), so the token is passed
as a query param instead: `/ws/documents/{id}?token=...`. The frontend's
`ws.js` does this automatically.

Set `JWT_SECRET` (and `SECRET_KEY`) to a real random value in production —
the defaults in `.env.example` are placeholders and must not be used as-is.

**Frontend auth**: `src/auth/AuthContext.jsx` holds the current user and
token (token in `localStorage`, fine here since this is a real deployed
app rather than an in-chat artifact sandbox). `src/auth/ProtectedRoute.jsx`
redirects to `/login` if there's no valid session. Login/Signup pages are
at `/login` and `/signup`.

This was tested end-to-end against the real running server: signup,
duplicate-email rejection, weak-password rejection, correct/incorrect
login, two separate users each only seeing their own projects, cross-user
access to another user's project/document/WebSocket correctly rejected
(404 for HTTP, WS closed with 403) rather than leaking existence, and an
authorized WebSocket connection succeeding and receiving the live status
stream.

## Testing performed

This was run end-to-end, not just written and assumed correct:

- Generated 5 real test documents spanning every required format: a
  digital PDF contract, a DOCX NDA, an XLSX invoice, a PNG scanned invoice
  (for the OCR path), and a digital PDF financial statement — several with
  deliberately planted issues (a math-mismatched total, a duplicate line
  item, a past due date, mismatched payment terms between two contracts,
  liabilities exceeding assets).
- Ran the actual stack: real Redis, a real Celery worker process, a real
  FastAPI process, real HTTP multipart uploads, and a real WebSocket
  client consuming the live stage-by-stage stream — not direct function
  calls standing in for the API.
- Every planted anomaly was correctly detected (amount mismatch, duplicate
  line item, past due date, liabilities > assets, mismatched payment
  terms), Stage 5 contradiction detection fired automatically after the
  second document in the project completed, and the CRM sync task hit the
  real Notion API, got a 403 (no credentials configured in this test
  environment), and recorded a `failed` sync status with the retry
  control intact rather than crashing the pipeline.
- One environment-specific substitution: this sandbox's network allowlist
  blocks the `en_core_web_sm` spaCy model download (Railway/Docker builds
  have unrestricted internet, so this is a sandbox limitation, not a
  product bug). Stage 1 was tested with a lightweight stand-in NER model
  so the real `classification.py` code path still executed; the shipped
  code and Dockerfile are unmodified and point at the real model.

**Three real bugs found and fixed during this pass:**
1. **OCR discarded all line structure** — `pytesseract` word output was
   being space-joined with no newlines, so line-anchored regexes (due
   date, vendor) would overshoot into the next printed line. Fixed by
   grouping words by Tesseract's line/paragraph/block indices before
   joining.
2. **XLSX header detection assumed row 0 was the header** — real invoices
   have a metadata preamble (Invoice Number, Vendor, Due Date) above the
   actual line-item table, so column matching silently failed and no line
   items were extracted. Fixed by scanning for the row that actually
   contains header-like vocabulary (`description`, `qty`, `amount`, etc.)
   rather than assuming it's first.
3. **Once the header was found correctly, trailing Tax/Total/Subtotal
   rows got misread as line items**, inflating the reconciliation sum.
   Fixed by excluding known summary-row labels from line-item parsing.

**One real limitation surfaced by testing, not yet fixed:** scanned
images/PDFs go through the OCR path, which currently produces plain text
with no table structure, so invoice line items can't be extracted for
*scanned* invoices the way they can for digital PDF/XLSX ones (total, tax,
due date, and vendor still extract fine via regex on the OCR text). Digital
PDF/DOCX/XLSX invoices are unaffected. Fixing this properly means adding
table-region detection to the OCR path (e.g. via layout analysis on word
bounding boxes) — flagged as a next step rather than silently shipped.

### Automated test suite

Manual end-to-end runs like the above are good for catching integration
bugs, but nothing stopped a future change from silently reintroducing
them. `backend/tests/` has 55 pytest tests covering:

- **Regression tests for all three bugs above** (`test_ocr.py`,
  `test_ingestion.py`, `test_extraction.py`) — a synthetic pytesseract
  data dict that reproduces the exact line-merging failure, an XLSX
  fixture with a metadata preamble above the real header row, and a
  fixture with trailing Tax/Total rows that previously leaked into
  line items.
- Anomaly detection for all three document types (amount mismatch,
  duplicate line items, past-due dates, short termination notice, long
  payment terms, asymmetric liability caps, missing clauses, liabilities
  exceeding assets, YoY threshold breaches).
- Risk scoring (severity weighting, category breakdown, the 100-point cap).
- Contradiction detection (revenue-vs-invoice-total, mismatched payment
  terms between documents sharing a party, and the negative cases —
  no false positive when values are close or parties don't overlap).
- Auth and multi-tenancy, against the real FastAPI app via `TestClient`
  (not reimplemented logic): signup validation, login success/failure,
  token validation, and — the important one — that a second user
  actually cannot see or touch a first user's projects/documents, with a
  plain 404 rather than a leak.

Run them with:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Requires a local Redis (rate limiting and the WebSocket pub/sub bridge
are both Redis-backed, and the FastAPI app's startup connects to Redis
even under `TestClient`). `docker compose up redis` is the easiest way to
get one for a bare test run. Stage 1's NER step is monkeypatched to a
tiny local stand-in model in tests (see `conftest.py`) so the suite
doesn't depend on downloading `en_core_web_sm` on every run — the
shipped application code is untouched and uses the real model.

## Scaling to concurrent users

None of this is required to *run* the app, but it's what would actually
break first under real concurrent load (targeted at "what happens with
~1000 concurrent users" specifically), and what's already been fixed vs.
what's a known next step:

**Fixed in this pass:**
- **DB connection pool was implicit/default** (5 connections + 10
  overflow), which exhausts fast once requests are actually concurrent
  rather than sequential. `database.py` now sets explicit `pool_size`,
  `max_overflow`, and `pool_recycle` for Postgres (SQLite doesn't have a
  real pool regardless — see below).
- **Every Redis publish opened a brand-new TCP connection.**
  `publish_stage_update()` (called on every one of a document's ~6 stage
  transitions) was creating and tearing down a fresh Redis client per
  call. At real concurrency that's thousands of short-lived connections
  per minute, risking Redis's max-clients limit. Fixed with a
  module-level connection pool reused across calls.
- **WebSocket fan-out was sequential.** The Redis-subscriber loop that
  forwards stage updates to browser sockets used a `for` loop with
  `await ws.send_text(...)` one at a time — a single slow or half-open
  browser tab would delay delivery to every other socket waiting on any
  document, since it's one shared listener task. Fixed with
  `asyncio.gather` so sends happen concurrently and a stuck socket only
  fails its own send.
- **No rate limiting on login/signup.** Unbounded auth endpoints are
  themselves a load risk (brute-force traffic, scripted signup spam) as
  much as a security one. Added a Redis-backed fixed-window limiter
  (`app/rate_limit.py`) — Redis-backed specifically because the app runs
  as multiple worker processes (see below), so an in-memory counter
  would only see the fraction of requests that happened to land on one
  process.
- **Single uvicorn worker process.** `Procfile`'s `web` process now runs
  `--workers ${WEB_WORKERS:-2}` (configurable). This is safe with this
  app's design specifically because the WebSocket fan-out goes through
  Redis pub/sub rather than in-process state — every worker process (and
  every Railway replica) subscribes to the same `doc:*` pattern and
  independently forwards to whichever sockets it happens to hold, so
  scaling to N processes doesn't require sticky sessions or a shared
  in-memory socket registry.
- Foreign key columns used in frequent filter queries (`Document.project_id`,
  `Anomaly.document_id`, `PipelineStageResult.document_id`,
  `Contradiction.project_id`, `CrmSyncRecord.document_id`) now have
  `index=True` — previously unindexed, meaning every "list documents for
  this project" / "list anomalies for this document" query was a table
  scan.

**Known next steps, not yet done:**
- **SQLite is a dev/demo default, not a concurrent-load target.** It's
  single-writer regardless of any pool settings. `DATABASE_URL` must
  point at Postgres (Railway's Postgres plugin, or any managed Postgres)
  before this could handle real concurrent traffic — the connection pool
  tuning above assumes Postgres.
- **No schema migration system.** `init_db()` is a one-time
  `Base.metadata.create_all()` — fine for a first deploy, but any future
  schema change against a live database needs a real migration tool
  (Alembic) rather than hand-editing a running Postgres instance.
- **Celery worker concurrency and replica count aren't auto-scaling.**
  Under sustained high upload volume, the fix is horizontal — run more
  `worker` replicas on Railway (each is a separate process pulling from
  the same Redis queue, so this requires no code change) — but nothing
  currently detects load and scales automatically.
- **The Redis pub/sub bridge subscribes to one global `doc:*` pattern**
  rather than dynamically subscribing/unsubscribing per active document.
  This is simple and correct, but at very high documents-in-flight counts
  it means every worker process receives every document's messages
  regardless of whether it holds that document's WebSocket — an
  optimization opportunity if channel volume ever becomes the bottleneck,
  not something that's broken today.
- **bcrypt's cost factor is a deliberate CPU/security tradeoff.** Under
  very high concurrent login volume this becomes a real throughput limit
  (that's the point of bcrypt), so it's not "fixed" so much as flagged:
  if login latency under load ever becomes a problem, the answer is
  horizontal scaling of the web process, not lowering the work factor.

## Configurable anomaly thresholds

Set via environment variables (see `backend/.env.example`):
`MIN_TERMINATION_NOTICE_DAYS`, `MAX_PAYMENT_TERMS_DAYS`,
`YOY_CHANGE_THRESHOLD_PCT`, `OCR_CONFIDENCE_THRESHOLD`.

## Known scope boundaries / next steps

Bonus features (clause-by-clause template comparison, exportable PDF
reports, natural-language document Q&A with citations, multi-language
support) are intentionally not included in this pass so the required
Sections 1–4 pipeline is solid rather than partially stubbed. Each has a
natural extension point:
- **PDF export** — a new endpoint rendering `Document` + `Anomaly` +
  risk data through a server-side PDF library (e.g. WeasyPrint), reusing
  the same data already in `extracted_entities`/`risk_breakdown`.
- **Document QA** — a new Stage 6 task that indexes `normalized_structure`
  sections and answers questions via a small extractive-QA pass, citing
  the matched section.
- **Clause comparison** — a project-level endpoint that runs
  `extraction.extract_contract_or_nda` on two documents and diffs the
  `clauses` dicts.
- **Multi-language** — swap spaCy's `en_core_web_sm` for a language
  detected via `langdetect`, loaded through the same `model_manager`
  cycling logic so the memory budget still holds.
