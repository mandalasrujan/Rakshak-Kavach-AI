# Milestone Report: M12 — Secure Patient Data Deletion

## 1. Objective
Let a patient delete a document and everything derived from it — stored file, chunks and embeddings, lab results, medications, and conversations that cited it with their checkpoints — safely, retryably, and without background jobs recreating data.

- **Spec deliverable:** one cascade service covering the file, rows, chunks, labs, medications, and citing chats with their checkpoints. Snapshot/share invalidation applies once those exist (M13/M14).
- **Spec "done when":** a deleted document can't be reached through chat, dashboard, history or any share.

## 2. Implementation
`DELETE /api/v1/patient/documents/{id}` (authenticated; same-site/CSRF; consent not required) calls `DocumentDeletionService.delete()`:
1. `SELECT … FOR UPDATE` on the patient's own row; anyone else gets 404. Ownership is enforced by RLS plus an explicit filter.
2. Delete the stored file. A storage error returns 503 and changes nothing in the database, so the request can be retried.
3. In one transaction:
   - delete chats found through `message_citations`; their checkpoints, pending writes and citations cascade;
   - delete the document; chunks with embeddings, lab results and medications cascade;
   - append the audit event `document.deleted`, whose metadata is counts only;
   - commit.
4. **Worker race:**
   - The processor re-locks the row (`get_for_update`) before writing anything.
   - If the document was deleted mid-job, it rolls back and returns `missing`.
   - If the worker holds the lock first, deletion waits and then removes what the worker wrote.
   - Foreign keys also make inserts for a deleted document impossible.
5. **Pending jobs:** jobs carry IDs only. A queued job for a deleted document finds no row and is a no-op. Jobs are not removed from Redis, and no PHI sits in Redis.
6. `DELETE /api/v1/patient/chats/{id}` (M10) deletes a single conversation the same way.

## 3. Important files
- **New:** `backend/app/services/document_deletion.py`, migration `0009_document_deletion.py`, `tests/integration/test_document_deletion.py`.
- **Modified:**
  - `repositories/document_repository.py` (`get_for_update`).
  - `services/document_processing.py` (re-lock before write).
  - `api/v1/documents.py` (DELETE route), `api/deps.py`.

## 4. Design decisions
- **File first, then database:** this ordering is what makes deletion retry-safe, because a failure can't leave a missing database row pointing at an orphaned PHI file. The opposite failure (file gone, rows intact) is only reachable until the retry succeeds.
- **Database cascades plus row locks rather than application loops:** one transaction, no partial states, and workers serialised against deletion.
- **Audit integrity:** `audit_log` has no FK and is append-only (trigger plus privileges). Deletion adds an event with counts only, and earlier events keep IDs and codes but no content.
- **Scope:** per-document deletion, as the spec defines M12. Whole-account deletion is not in the spec and was not added.

## 5. Database changes (0009)
`GRANT DELETE ON documents TO rakshak_app`. The cascades were defined in 0003–0008.

## 6. Tests and results
| Test | Scenario | Result |
|---|---|---|
| `test_deletion_removes_the_document_and_everything_derived_from_it` | 0 rows left in documents/chunks/lab_results/medications/message_citations; file removed; citing chat and checkpoints removed; unrelated chat kept; audit has counts only; 404 on GET; labs/trends no longer include it; `/ask` cannot cite it; deleted chat history 404 | **PASSED** |
| `test_deletion_is_patient_scoped_and_needs_no_consent` | other patient 404, row intact; owner deletes after revoking consent | **PASSED** |
| `test_deletion_requires_auth_and_csrf` | 401 / 403 | **PASSED** |
| `test_storage_failure_changes_nothing_and_retry_succeeds` | 503 with all rows intact → retry 204 → repeat 404 | **PASSED** |
| `test_pending_job_after_deletion_recreates_nothing` | queued job runs after deletion → `missing`, no rows | **PASSED** |
| `test_deletion_during_processing_recreates_nothing` | patient deletes while the worker embeds → `missing`, no rows | **PASSED** |
| `test_reupload_after_deletion_creates_a_new_document` | dedup does not block a fresh upload | **PASSED** |

- **Full suite:** 289 passed. Ruff and format are clean.
- **Native run:**
  - Before deletion: 2 chunks and 1 lab result.
  - DELETE returned 204; a repeat returned 404.
  - Afterwards: document, chunks, lab results and the citing chat all at 0; storage files went from 3 to 2.
  - Audit metadata: `{"chats": 1, "chunks": 2, "lab_results": 1, "medications": 0}`.

## 7. Security considerations
- Only the authenticated owner can delete; there is no existence leak (404).
- CSRF/same-site checks apply.
- Deletion is allowed without consent, so patients can always remove their own data.
- Logs and audit carry IDs and counts only.

## 8. Known limitations
- If the file is deleted but the database transaction then fails, the document row remains (with a missing file) until the patient retries.
- Queued ARQ jobs are left to no-op rather than being aborted.
- Snapshot and share invalidation will be added with M13/M14.
- No whole-account deletion.
- Database backups (M17 runbook) would still contain deleted data until they rotate.

## 9. Verification status
**`M12: COMPLETED AND VERIFIED`**
