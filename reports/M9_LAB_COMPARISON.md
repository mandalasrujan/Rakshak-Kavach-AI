# Milestone Report: M9 — Lab Comparison

## 1. Milestone Title and Objective
- **Milestone:** M9 — Lab Comparison
- **Status:** COMPLETED
- **Objective:** Deterministic previous-vs-latest comparison of normalized results per canonical test, with provenance, and no LLM involvement.

## 2. Why This Milestone is Necessary
Trend questions ("is my HbA1c getting worse?") must never depend on LLM arithmetic. M10's `get_labs` tool will return these computed results for the model to explain.

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:** plain-Python previous-vs-latest comparison, no LLM imports.
- **Acceptance Criteria:** "Tests pass for rising, falling, unchanged, missing, convertible units, unconvertible units, renamed test, ambiguous date."

## 4. Architecture and Implementation
```
LabService.trends() ─► group normalized results by test_code (unknown tests skipped)
                    ─► compare(points)   [app/services/lab_comparison.py: stdlib only]
GET /api/v1/patient/labs/trends?test_code=  → items + fixed note
```
Rules:
1. Usable = status `ok`, canonical value and a date (collected, else reported). History sorted by date.
2. Fewer than 2 usable: `not_comparable/incompatible_units` if a unit could not be converted, else `insufficient_data` (`single_result`, `missing_value`, `missing_date`).
3. Ambiguous DD/MM dates: every day/month reading is tried; if the latest two can change, `not_comparable/ambiguous_date_order`. Same date → `not_comparable/same_date`.
4. `change = latest − previous` (canonical units), `percent_change` (none if previous is 0); `direction` rising/falling/unchanged with a 2% tolerance.
5. Status vs each report's own reference range: closer → `improved`, further → `worsened`, both inside or within tolerance → `stable`; no range → `insufficient_data/no_reference_range` (direction still shown).
- Every point carries `result_id`, `document_id`, `chunk_id`, `page`, raw value and unit.
- Fixed note: "…compared with the reference range printed on its own report. This is not a diagnosis; discuss any changes with your doctor."

## 5. Files and Folders Created or Modified
- New: `backend/app/services/lab_comparison.py`; `tests/unit/test_lab_comparison.py`, `tests/integration/test_lab_trends.py`.
- Modified: `services/lab_service.py` (`trends`), `schemas/lab.py`, `api/v1/labs.py`.

## 9–10. Testing and Results
| Test | Scenario | Result |
|---|---|---|
| rising/worsened, falling/improved, unchanged/stable, in-range/stable | core cases with exact change and percent | **PASSED** |
| multiple history | latest two compared; history ordered | **PASSED** |
| single, missing value, incompatible units, missing date, same date, empty | never compared | **PASSED** |
| no reference range | direction only | **PASSED** |
| ambiguous date | order-flipping → not comparable; order-safe → compared | **PASSED** |
| determinism | shuffled inputs give identical output | **PASSED** |
| zero previous | no percent change | **PASSED** |
| no LLM imports | AST check: stdlib only | **PASSED** |
| no diagnostic claims | statuses from a fixed set; no diagnosis/treatment wording | **PASSED** |
| `test_trends_across_renamed_tests_and_units` | real uploads: HbA1c 7.1 → Glycated Haemoglobin 7.6 = worsened, +0.5, +7.04%; cholesterol 212 mg/dL vs 5.9 mmol/L (228.153) = +16.153 worsened; HDL stable inside range; single glucose insufficient with ambiguous-date flag; provenance ids | **PASSED** |
| `test_trends_are_patient_scoped` | other patient's results invisible | **PASSED** |
| `test_trends_require_auth` | 401 | **PASSED** |

## 12. Verification Results
Full suite 241 passed; Ruff/format clean. Native run: `/labs/trends?test_code=HBA1C` → `worsened rising 0.5 (7.1 -> 7.6)`.

## 13. Limitations and Pending Work
- "Improved/worsened" is relative to reference ranges only, not clinical significance; the 2% stability tolerance is a fixed constant pending clinician review.
- The LLM explaining these results is M10 (`get_labs` tool).

## 14. Final Milestone Status
**`M9: COMPLETED AND VERIFIED`**
