# Milestone Report: M5 — Table-Aware Extraction

## 1. Milestone Title and Objective
- **Milestone:** M5 — Table-Aware Extraction
- **Status:** COMPLETED
- **Objective:** Turn each uploaded digital PDF into `chunks`: one `lab_row` record per lab-table row and `narrative` chunks for all other text, each with its page number.

## 2. Why This Milestone is Necessary
Lab reports are tables. Plain text extraction scrambles rows, so a value can be separated from its test name, unit or reference range. Keeping each row whole is the basis for correct retrieval (M6/M7), validated structured extraction (M8) and page-level citations.

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:** PyMuPDF text + `find_tables`, one record per lab row, narrative chunks with page metadata; `chunks` table (id, patient_id, document_id, page, kind narrative/lab_row, text; btree index on patient_id); LangChain only for text splitting; no OCR.
- **Acceptance Criteria ("Done when"):** "Synthetic lab PDFs produce one row per test with correct page numbers."

## 4. Architecture and Implementation
```
DocumentProcessor (worker) ─► extract_pdf(bytes) in a thread
   per page: find_tables()
     lab table (has test + result column) → one lab_row chunk per row
       "Test: Hemoglobin; Result: 12.4; Unit: g/dL; Reference Range: 12.0 - 15.5"
     other tables (patient details, prescriptions) → row text added to the page narrative
     text blocks outside table areas → page narrative (reading order by y)
     page narrative → RecursiveCharacterTextSplitter(1000, overlap 150) → narrative chunks
   no chunks at all → failed: no_text_layer
 ─► ChunkRepository.replace_for_document (delete + insert) + status ready + audit, one transaction
```
### 4.1 Key Design Choices
- Lab tables are recognised by headers (a test-name column and a result column), not by position, so patient-detail and prescription tables never become lab rows.
- Lab rows keep the report's own header labels, unit and reference range in one record (reference ranges stay per result, per spec section 4).
- Text inside table areas is excluded from the narrative to avoid duplicates; non-lab tables are rendered row by row instead.
- Chunks are replaced, not appended, in the same transaction as the `ready` status, so retries and crash recovery never duplicate chunks.
- Image-only/scanned PDFs fail with `no_text_layer` (no OCR in v1).
- Embedding columns are deliberately not created; they arrive with pgvector in M6.

## 5. Files and Folders Created or Modified
- `backend/app/services/extraction.py`: `extract_pdf`, `ExtractedChunk`, `ExtractionResult`.
- `backend/app/models/chunk.py`, `backend/alembic/versions/0004_chunks.py`, `backend/app/models/__init__.py`.
- `backend/app/repositories/chunk_repository.py` (patient-scoped).
- `backend/app/services/document_processing.py`: extraction + chunk replacement; audit counts.
- `backend/app/services/pdf_validation.py`: removed the now-unused page counter (validation shared via `open_pdf`).
- `requirements.txt`: `langchain-text-splitters`.
- Tests: `tests/unit/test_extraction.py`, `tests/integration/test_document_processing.py` (chunk tests).

## 6. Important Classes, Functions and APIs
- `extract_pdf(data, *, max_pages) -> ExtractionResult` — raises `PdfRejectedError` (`unreadable_pdf`, `encrypted_pdf`, `too_many_pages`, `no_text_layer`). CPU-bound; called via `asyncio.to_thread`.
- `ChunkRepository(session, patient_id).replace_for_document(document_id, chunks)`.
- No new HTTP endpoints (chunks are internal until retrieval in M6/M7).

## 7. Database Changes
- **Migration:** `0004_chunks.py`.
- `chunks`: `id`, `patient_id` (FK `patients`, CASCADE, btree index), `document_id` (FK `documents`, CASCADE, index), `page`, `kind` (CHECK narrative/lab_row), `text`.
- **RLS:** not yet (M6).

## 8. Security Considerations
- Every chunk carries the owner's `patient_id`; the repository is constructed with it and deletes/inserts only within that patient's rows (cross-patient test with the same file).
- Prompt-injection text inside PDFs (synthetic file 10) is stored verbatim as data; it is never executed. Treating it as data in prompts is M10.
- Extracted text never appears in logs or audit metadata (audit stores counts only; verified in the native run).

## 9. Testing Methodology
The acceptance test is derived from the generator's own data: for every synthetic lab report, the extracted `lab_row` sequence must equal the generator's rows, in order, with the expected page. Integration tests run the real worker pipeline against PostgreSQL. A native run of the full stack (migrations from Phase 1's database, API, `arq` CLI worker) confirmed the same result end to end.

## 10. Test Cases and Actual Results
| Test File | Test Case Name | Purpose / Scenario Tested | Result |
|---|---|---|---|
| `tests/unit/test_extraction.py` | `test_lab_reports_produce_one_row_per_test_with_correct_pages` (9 lab reports) | **Acceptance:** exact rows, order and pages (incl. 2-page CBC/LFT, mmol/L, µmol/L, mmol/mol, renamed test) | **PASSED** |
| | `test_non_lab_documents_become_narrative_only` (5) | Prescription, note, MRI, CT, injection PDF → narrative only | **PASSED** |
| | `test_long_narrative_is_split_and_keeps_page_numbers` | Splitting ≤ 1000 chars with correct pages | **PASSED** |
| | `test_image_only_pdf_is_rejected_without_ocr` | `no_text_layer` | **PASSED** |
| `tests/integration/test_document_processing.py` | `test_processing_stores_patient_scoped_chunks` | Chunks per patient; 6 + 5 lab rows on pages 1 and 2; audit counts | **PASSED** |
| | `test_reprocessing_after_a_crash_replaces_chunks` | No duplicates after a crashed attempt | **PASSED** |
| | `test_image_only_upload_fails_with_no_text_layer` | Failed status, no chunks | **PASSED** |
| `tests/integration/test_infrastructure.py` | migrations up/down, models match | 0004 reversible and in sync | **PASSED** |

## 11. Problems Encountered and Fixes
1. **PyMuPDF prints a layout-package hint to stdout** on first table detection, which would break JSON log lines. Disabled with `pymupdf.no_recommend_layout()`.
2. **Layering:** the chunk repository references the extraction dataclass only for typing (no runtime import from services).

## 12. Verification Results
- **Pytest (full Phase 2 suite):** 125 passed, 0 failed, 0 skipped.
- **Linter:** `ruff check .` clean; `ruff format --check .` 96 files compliant.
- **Native end-to-end run:** `alembic upgrade` 0001 → 0004 on the existing database; `arq --check` healthy; upload → 202 → `ready` with `pages: 2`; chunks: lab_row page 1 = 6, page 2 = 5, narrative 1 per page; duplicate upload 200; logs contain no names, values or credentials.
- **Docker Compose:** config valid; images not rebuilt in this sandbox (Docker Hub unreachable).

## 13. Limitations and Pending Work
- Lab-table detection relies on header words (`test`/`investigation`/`parameter`/`analyte` + `result`/`value`); unusual real-world layouts may be missed. Value validation and normalization are M8.
- Narrative chunk size (1000/150) has not been tuned yet; tuning belongs with the retrieval eval (M7).
- Embeddings and RLS on `chunks` are M6.

## 14. Final Milestone Status
**`M5: COMPLETED AND VERIFIED`** — synthetic lab PDFs produce exactly one `lab_row` per test with correct page numbers, stored per patient and idempotently.
