# Milestone Report: M4 — Upload and Queue

## 1. Milestone Title and Objective
- **Milestone:** M4 — Upload and Queue
- **Status:** COMPLETED
- **Objective:** Accept digital PDF uploads with a 202 response, store them under random keys behind a storage interface, track document status, and process them asynchronously in an idempotent, retrying ARQ job.

## 2. Why This Milestone is Necessary
Extraction and embedding take seconds to minutes and must not run inside a request. Uploads are also the main untrusted input: type, size and page limits, and per-patient dedup must be enforced before any parsing pipeline (M5+) exists.

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:** 202 upload, storage interface, document status, ARQ worker with retries and idempotent jobs, magic-byte check, size and page limits, per-patient dedup; random storage keys; `documents` table (id, patient_id, storage_key, file_hash, status, failure_reason, pages, uploaded_at; unique (patient_id, file_hash)).
- **Acceptance Criteria ("Done when"):** "Upload goes queued → ready; the same file from a second patient is accepted."

## 4. Architecture and Implementation
```
POST /api/v1/patient/documents  (auth + same-site/CSRF + require_consent)
  └─► read ≤ MAX_UPLOAD_MB ─► DocumentService.upload
        magic bytes "%PDF-" → sha256 → per-patient dedup
        → storage.put(patients/<patient_id>/<random>.pdf) → documents row (queued) + audit
        → ArqRedis.enqueue_job("process_document", document_id, patient_id)
Worker: process_document (thin) ─► DocumentProcessor.process
        scoped load → terminal? skip → consent still active? → processing
        → PyMuPDF validation in a thread (encrypted / unreadable / page limit) → ready | failed + audit
```
### 4.1 Key Design Choices
- **Untrusted PDF parsing only in the worker.** The API checks size and magic bytes; page counting, encryption and corruption checks run in the worker.
- **Dedup per patient:** a duplicate from the same patient returns the existing document (200); a previously failed duplicate is re-queued (202); another patient's identical file is a new document (no cross-patient existence leak).
- **Idempotent jobs:** `ready`/`failed` documents are skipped; a document left `processing` by a crash is reprocessed. Job args are IDs only.
- **Retries:** unexpected errors raise `arq.Retry` with backoff for up to 3 tries; the last try marks the document `failed` (`processing_error`) so nothing stays queued forever.
- **Consent re-checked in the worker**, so revoking consent after upload stops processing (`consent_revoked`).
- **Enqueue failure** marks the document `failed` (`enqueue_failed`) and returns 503; re-uploading the file re-queues it.
- `DocumentRepository` requires `patient_id` at construction; a job with the wrong patient ID cannot load the document.
- PyMuPDF pinned to 1.28.2 (2.x pulls ONNX layout models we do not need).

## 5. Files and Folders Created or Modified
- `backend/app/core/storage.py`: `ObjectStorage` protocol, `LocalObjectStorage` (atomic writes, key validation, 0600 files), `create_storage`.
- `backend/app/models/document.py`, `backend/alembic/versions/0003_documents.py`.
- `backend/app/repositories/document_repository.py` (patient-scoped).
- `backend/app/services/pdf_validation.py`, `document_service.py`, `document_processing.py`.
- `backend/app/schemas/document.py`, `backend/app/api/v1/documents.py`, `router.py`, `deps.py` (`get_document_service`).
- `backend/app/main.py`: ARQ client and storage created in lifespan.
- `backend/app/core/config.py` (`storage_*`, `max_upload_mb`), `backend/app/core/errors.py` (404/413/415).
- `worker/main.py` (`process_document`, startup/shutdown resources, `max_tries`, `job_timeout`), `worker/config.py` (`database_url`, storage, `max_pdf_pages`).
- `docker-compose.yml` (shared `storage` volume; worker gets DB URL and waits for migrations), `backend/Dockerfile`, `worker/Dockerfile` (`/data/storage` owned by the non-root user), `.env.example` (limits now real defaults), `requirements.txt` (`python-multipart`, `PyMuPDF`), `pyproject.toml` (Ruff: `fastapi.File`, `ASYNC240` in tests).
- Tests: `tests/integration/test_documents.py`, `tests/integration/test_document_processing.py`, `tests/unit/test_storage.py`, `tests/integration/test_worker.py` (retry test; fixture now sets `DATABASE_URL`), `tests/conftest.py` (per-test storage dir, `synthetic_dir`), `tests/helpers.py` (`upload`).

## 6. Important Classes, Functions and APIs
- `POST /api/v1/patient/documents` (multipart `file`) → 202 `DocumentRead` | 200 duplicate | 403 `consent_required` | 413 `file_too_large` | 415 `unsupported_file_type` | 503 queue unavailable.
- `GET /api/v1/patient/documents?limit=&offset=` → `{items, total, limit, offset}` (newest first).
- `GET /api/v1/patient/documents/{id}` → `DocumentRead` or 404 (also for other patients' IDs).
- Failure reasons: `encrypted_pdf`, `unreadable_pdf`, `too_many_pages`, `consent_revoked`, `enqueue_failed`, `processing_error`.

## 7. Database Changes
- **Migration:** `0003_documents.py`.
- `documents`: columns per spec; FK `patients` ON DELETE CASCADE; unique (`patient_id`, `file_hash`); unique `storage_key`; CHECK on `status`.
- **RLS:** not yet (M6).

## 8. Security Considerations
- Consent required for upload; CSRF/same-site and auth inherited from M2 routers.
- Type decided by magic bytes, not by file name or client content type; client file names are never stored.
- Storage keys are random, validated against traversal, written atomically with mode 0600.
- Audit events: `document.uploaded` (size only), `document.requeued`, `document.ready` (pages), `document.failed` (reason). No content or file names in logs or audit.

## 9. Testing Methodology
Integration tests use the real API, PostgreSQL and Redis, and the deterministic synthetic PDFs. Queue → worker is verified with a real `arq.Worker` in burst mode running the real `process_document` job. Invalid PDFs are generated with PyMuPDF (encrypted) or hand-crafted bytes.

## 10. Test Cases and Actual Results
| Test File | Test Case Name | Purpose / Scenario Tested | Result |
|---|---|---|---|
| `test_documents.py` | `test_upload_requires_active_consent` | 403 before consent and after revoke (M3 acceptance) | **PASSED** |
| | `test_upload_stores_file_queues_job_and_audits` | 202, random key, stored bytes, job args, audit | **PASSED** |
| | `test_non_pdf_content_is_rejected_by_magic_bytes` (3 cases) | 415, nothing stored | **PASSED** |
| | `test_oversized_upload_is_rejected` | 413 above limit | **PASSED** |
| | `test_dedup_is_per_patient` | 202 → 200 duplicate; second patient 202 | **PASSED** |
| | `test_documents_are_scoped_to_their_owner` | 404 for another patient's ID; empty list | **PASSED** |
| | `test_list_is_paginated_newest_first` | Pagination and validation | **PASSED** |
| | `test_document_routes_require_auth_and_csrf` | 401 / 403 | **PASSED** |
| | `test_enqueue_failure_marks_failed_and_reupload_requeues` | 503 → failed → re-queue 202 | **PASSED** |
| | `test_upload_goes_queued_to_ready_through_the_worker` | **Acceptance:** queued → ready via ARQ worker | **PASSED** |
| `test_document_processing.py` | `test_invalid_pdfs_fail_with_reason` (3 cases) | encrypted / page limit / corrupt | **PASSED** |
| | `test_revoked_consent_stops_processing` | `consent_revoked` | **PASSED** |
| | `test_processing_is_idempotent_and_patient_scoped` | Wrong owner → missing; one `document.ready` event | **PASSED** |
| `test_worker.py` | `test_process_document_retries_then_marks_failed` | `Retry` then `processing_error` | **PASSED** |
| `tests/unit/test_storage.py` | round trip, unsafe keys (6), unknown backend | Storage safety | **PASSED** |

## 11. Problems Encountered and Fixes
1. **PyMuPDF 2.x dependency weight:** 2.1 pulls `onnxruntime`, `numpy` and layout packages. Pinned 1.28.2, which has no dependencies and includes `find_tables`.
2. **Ruff B008/ASYNC240:** added `fastapi.File` to immutable calls; allowed blocking file reads in tests.

## 12. Verification Results
- **Pytest:** M4-relevant tests 31 passed; full-suite and native-stack results in the tracker.
- **Linter:** `ruff check .` and `ruff format --check .` clean.
- **Docker Compose:** `docker compose config` valid. Images were not built in this sandbox (Docker Hub unreachable); rebuild locally with `docker compose up --build --wait`.

## 13. Limitations and Pending Work
- The multipart body is spooled to a temp file by Starlette before the size check; production should also set a body-size limit at the reverse proxy.
- Original file names are not stored (possible PHI); the dashboard (M15) will identify documents by date and type.
- Document deletion (file + rows + derived data) is M12.

## 14. Final Milestone Status
**`M4: COMPLETED AND VERIFIED`** — upload, validation, dedup, scoping, queueing, retries and queued → ready are implemented and tested.
