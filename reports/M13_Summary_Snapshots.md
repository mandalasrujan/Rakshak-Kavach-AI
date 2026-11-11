# Milestone Report: M13 — Summary Snapshots

## Objective
Patient summary snapshots built from the patient's own records, with page-level provenance, versioning, approval and immutability. The doctor (M14) sees only an approved snapshot.

- **Spec deliverable:** medication and lab sections built from SQL, plus a short guard-checked narrative labelled AI-generated; a preview and approve UI.
- **Spec "done when":** a schema-valid snapshot is produced, and an injection PDF can't change the medication section.

## Implementation
- **`POST /api/v1/patient/snapshots`** (consent required) builds a new version:
  - `medications`: from the M10 table, each with document, page, chunk and excerpt.
  - `labs`: M9 deterministic comparisons with the latest and previous values and their sources.
  - `documents`: the ready documents.
  - `missing`: an explicit "not found" statement for each empty section.
  - `narrative`: optional and labelled `ai_generated`. It is grounded on the structured sections (M10 `ground()`) and checked by the M11 output guard. Its status is `ok`, `empty`, `blocked` or `unavailable`; the text is kept only when the status is `ok`.
  - `note`: the fixed "not a diagnosis" note.
  - The content is validated against `SnapshotContent` (Pydantic, `extra="forbid"`, `schema_version` 1) before storage.
- **Other endpoints:** `GET /snapshots` lists all versions, newest first; `GET /snapshots/{id}` previews one; `POST /snapshots/{id}/approve` approves (consent required).
- **Approval:** approving twice is a no-op. Approved content is never modified, and new generations always create a new version (unique per patient and version number).
- **Deletion:** removing a source document (M12) invalidates every snapshot that used it, purges the content to `{"invalidated": true, "reason": "source_document_deleted"}`, and revokes its shares (M14).
- **Provenance:** `model` records `chat_model` (for example `fake-extractive`) or `none`. The audit log records version, counts and narrative status only.

## Files
- **New:** `backend/app/models/snapshot.py`, `backend/app/schemas/snapshot.py`, `backend/app/repositories/snapshot_repository.py`, `backend/app/services/snapshot_service.py`, `backend/app/api/v1/snapshots.py`, migration `0010_summary_snapshots.py`, `tests/integration/test_snapshots.py`.
- **Modified:**
  - `llm/base.py`, `llm/fake.py`, `llm/gemini.py`: `chat_model` attribute.
  - `repositories/chunk_repository.py`: `texts()`; `agent/tools.py` reuses it.
  - `services/document_deletion.py`: invalidation.
  - `api/deps.py`, `api/v1/router.py`, `models/__init__.py`, and one M12 test assertion (new audit key).

## Database (0010)
`summary_snapshots`:
- columns: `id`, `patient_id`, `version`, `content_json` (JSONB), `source_document_ids` (uuid[]), `model`, `generated_at`, `approved_at`, `invalidated_at`;
- unique on (`patient_id`, `version`);
- RLS `patient_isolation`; grants SELECT, INSERT and UPDATE only (no DELETE).

## Tests (11, all passed)
| Test | Result |
|---|---|
| Sections built from records: schema-valid, medications and labs with document/page/excerpt, HbA1c worsened +0.5 across a renamed test, 3 source documents | **PASSED** |
| Missing information stated explicitly (MRI-only patient) | **PASSED** |
| **Acceptance:** an injection PDF plus a hostile LLM narrative cannot change the medication section | **PASSED** |
| Narrative guarded: diagnosis → blocked, invented number → blocked, fabricated citation → empty, no LLM → unavailable; structured sections intact | **PASSED** (4) |
| Versions kept; approved snapshots never change; idempotent approval | **PASSED** |
| Patient scoping (404), consent and CSRF gates | **PASSED** |
| Deleting a source document invalidates and purges; approving an invalidated snapshot → 409 | **PASSED** |
| No medication names in logs | **PASSED** |

## Security considerations
- Grounded only in the patient's own rows (RLS-bound session).
- The LLM never writes structured sections.
- No diagnosis, prediction or treatment advice reaches the narrative (M11 guard).

## Known limitations
- The narrative is not evaluated on live Gemini.
- "Medical history" means the document list and the narrative; there is no clinical history extraction.
- Labs cover the latest two results per test only, not the full history.

## Status
**`M13: COMPLETED AND VERIFIED`**
