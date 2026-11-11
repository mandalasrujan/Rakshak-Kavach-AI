# Milestone Report: M8 — Extraction and Normalization

## 1. Milestone Title and Objective
- **Milestone:** M8 — Extraction and Normalization
- **Status:** COMPLETED
- **Objective:** Turn every lab-table row into a normalized result (canonical test code, numeric value, canonical unit/value, parsed reference range, report dates) while keeping the source text verbatim and a chunk/page/document provenance link.

## 2. Why This Milestone is Necessary
Comparisons (M9) are only safe if the same test under different names and units is recognised, and if every number can be traced back to the exact row it came from.

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:** test dictionary (~40 tests, versioned YAML), unit conversions as functions, same-row validation, plausibility bounds, DD/MM date parsing (prefer collection date, flag ambiguity); `lab_results` per spec section 4.
- **Acceptance Criteria:** "Mismatches rejected and logged; precision and recall measured on 10 labeled reports."

## 4. Architecture and Implementation
```
M5 lab_row chunk (header, cell) pairs ─► normalize_row()  [pure Python, no LLM]
   resolve_test (aliases, parentheses stripped) · parse_value · normalize_unit · parse_reference
   convert: canonical = slope × value + intercept · plausibility bounds
document narrative ─► parse_document_dates (DD/MM/YYYY; ambiguity flagged)
worker transaction: chunks + embeddings + lab_results (chunk_id FK) + status + audit
```
### 4.1 Key Design Choices
- **Deterministic parsing instead of Gemini extraction.** The spec names Gemini extraction into Pydantic schemas. Because M5 already yields structured table rows, values are taken verbatim from the row cells (same-row validation holds by construction) and no LLM touches numbers. LLM extraction for values outside tables is deferred (see section 13).
- Never "fixes" data: unusable rows are stored with a status — `unknown_test`, `missing_value`, `non_numeric_value`, `censored_value` (`<0.5`), `unknown_unit` (missing/unrecognised/not convertible for that test), `implausible_value` — with `canonical_value = NULL`, and logged (`lab.value_flagged`: document id, test code, reason only).
- Ambiguous number formats are rejected (`12,4`, `12.4.5`); thousands separators accepted (`1,234`).
- Reference ranges kept in source units and converted to canonical units; one-sided ranges (`< 200`, `> 40`, `Up to 40`) supported.
- `dictionary_version` stored on every result.
- Medications were not extracted in this phase (see section 13).

## 5. Files and Folders Created or Modified
- New: `backend/app/data/lab_tests.yaml` (47 tests), `backend/app/services/lab_normalization.py`, `backend/app/models/lab_result.py`, `backend/app/repositories/lab_result_repository.py`, `backend/app/services/lab_service.py`, `backend/app/schemas/lab.py`, `backend/app/api/v1/labs.py`, migration `0007_lab_results.py`.
- Modified: `services/extraction.py` (`ExtractedChunk.cells`), `services/document_processing.py`, `api/deps.py`, `api/v1/router.py`, `models/__init__.py`.
- Tests: `tests/unit/test_lab_normalization.py`, `tests/integration/test_labs.py`; `test_document_processing.py` audit expectation (`lab_results_flagged`).

## 6. Important Classes, Functions and APIs
- `GET /api/v1/patient/labs?test_code=&limit=&offset=` → normalized results with raw values, canonical values, ranges, dates, status, `document_id`/`chunk_id`/`page`.
- `normalize_row`, `resolve_test`, `normalize_unit`, `parse_value`, `parse_reference`, `parse_document_dates`, `load_dictionary`.

## 7. Database Changes
- 0007: `lab_results` (spec columns + `chunk_id` (unique FK), `raw_name/raw_value/raw_unit/raw_reference`, `canonical_ref_low/high`, `date_ambiguous`, `dictionary_version`); index (`patient_id`, `test_code`); grants SELECT/INSERT/DELETE; RLS policy.

## 9–10. Testing and Results
| Test | Scenario | Result |
|---|---|---|
| dictionary integrity | ≥40 tests, units known, no alias collisions | **PASSED** |
| equivalent names (12) | HbA1c / Glycated Haemoglobin / HbA1c (IFCC) / hemoglobin A1c → HBA1C, etc. | **PASSED** |
| units (10), numbers (11), ranges (10) | spelling variants incl. Greek mu; malformed/missing/censored values; one- and two-sided ranges | **PASSED** |
| conversions | glucose 7.4 mmol/L → 133.2 mg/dL; HbA1c 53 mmol/mol → 0.0915×53+2.15; creatinine µmol/L; ranges converted; raw kept | **PASSED** |
| unusable values (6) | incompatible/missing unit, implausible, unknown test, non-numeric, missing | **PASSED** |
| dates | DD/MM parsing, ambiguity flag, invalid and missing dates | **PASSED** |
| `test_synthetic_reports_precision_and_recall` | **acceptance:** hand-labelled ground truth for all 30 lab rows in 9 synthetic lab reports: precision 1.0, recall 1.0 | **PASSED** |
| determinism | identical output on repeat; mmol/L lipid canonical values | **PASSED** |
| `test_labs.py` (5) | provenance join to source chunk text and page; flagged values stored + logged without values; reprocessing replaces; RLS/patient scope; filters/validation/auth | **PASSED** |

## 11. Problems Encountered and Fixes
1. `"12.4.5"` was first accepted as 12.4 with `.5` read as a unit; values followed by digits, dots or commas are now `non_numeric_value`.
2. My first expected row count was 39; the synthetic reports contain 30 lab rows.
3. Log-PHI assertions searched raw log reprs and could match digits inside random UUIDs; they now check content fields only.

## 12. Verification Results
Full suite 241 passed; Ruff/format clean. Native run: 13 lab results from three uploaded reports.

## 13. Limitations and Pending Work
- Precision/recall measured on 9 synthetic lab reports (30 rows), not 10 hand-labelled real-world reports; the synthetic generator has 9 lab reports.
- No LLM-based extraction for values outside tables; no medication extraction (the `medications` table is needed by M10's `get_medications`).
- Dictionary coverage is 47 tests; unknown tests are stored but never compared.

## 14. Final Milestone Status
**`M8: COMPLETED AND VERIFIED`** (with the deviations above)
