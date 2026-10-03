# Ledgerline — Specification Coverage

This repository is the implementation baseline for the Intelligent Document Processing and Contract Intelligence Platform specification.

## Core requirements

| Requirement | Coverage | Implementation |
|---|---|---|
| PDF, DOCX, XLSX, JPG, PNG ingestion | Complete | Automatic extension/format routing in `pipeline/ingestion.py` |
| Digital PDF/DOCX structure preservation | Complete | Sections/headings/tables retained in normalized JSON |
| Scanned PDF/image OCR | Complete | Tesseract + OpenCV deskew + post-processing |
| OCR confidence warning | Complete | Configurable threshold; low-quality flag is persisted and shown in UI |
| XLSX data-sheet identification | Complete | Numeric-density/header heuristics exclude sparse metadata/chart-like sheets from structured tables |
| Real-time stage streaming | Complete | WebSocket + Redis pub/sub bridge |
| Document classification | Complete | Contract/invoice/financial statement/RFP/NDA/other classification plus parties/dates/jurisdiction |
| Entity and clause extraction | Strong | Type-specific extraction plus named-clause inventory and values; intentionally rule-based for CPU/memory constraints |
| Anomaly detection | Strong | Contract, invoice, and financial checks; severity + plain-English explanations; configurable financial ratio ranges |
| Risk scoring | Complete | 0–100 score and category breakdown |
| Cross-document contradictions | Strong | Payment terms, revenue-vs-invoice totals, party/vendor matching; explicit Stage 5 result |
| CRM sync | Complete | Notion/Airtable upsert by SHA-256 content hash; public document link |
| Projects/document grouping | Complete | Authenticated project and document views |
| Real-time processing UI | Complete | Stage-by-stage spinner/checkmark/output panels; Stage 5 shown explicitly |
| Document detail UI | Complete | Entities, dates, anomalies/evidence, risk breakdown, CRM status |
| Contradiction UI | Complete | Project-level side-by-side values |
| CRM retry UI | Complete | Failed sync retry control |
| CPU-bound / Railway memory constraints | Complete | Celery worker, lazy spaCy model loading, model cycling, idle unload, Tesseract external process |
| Public website deployment readiness | Prepared | Railway service layout, environment configuration, production public URL setting |

## Bonus tasks

The following are intentionally not required for the core implementation and remain optional:

- Clause-by-clause contract comparison
- Downloadable server-side PDF reports
- Citation-grounded document QA
- Multi-language extraction/output

## Production notes

1. Set `PUBLIC_APP_URL` to the deployed frontend URL before enabling CRM sync so CRM records contain clickable document links.
2. Configure Railway Postgres, Redis, web, worker, and frontend services as described in `README.md`.
3. Configure real JWT secrets and CRM credentials in Railway environment variables.
4. Install the production spaCy model during the backend image build; the test suite uses a lightweight test-only NER substitute.
