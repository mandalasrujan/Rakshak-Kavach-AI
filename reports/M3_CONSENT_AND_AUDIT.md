# Milestone Report: M3 — Consent and Audit

## 1. Milestone Title and Objective
- **Milestone:** M3 — Consent and Audit
- **Status:** COMPLETED
- **Objective:** Versioned, purpose-bound consent that patients can grant and revoke, a `require_consent` dependency that blocks data processing without active consent, and an append-only `audit_log`.

## 2. Why This Milestone is Necessary
Every later milestone processes patient documents and sends excerpts to Gemini. Processing must be gated on explicit consent to a notice that discloses this, and every consent change must leave a tamper-resistant trail. Retrofitting consent after uploads and chat exist is error-prone, so the gate exists before M4.

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:** versioned consent (notice states data is sent to Google's Gemini API), grant and revoke, `require_consent` dependency, audit log (`consent_records`, `audit_log` with IDs and metadata only).
- **Acceptance Criteria ("Done when"):** "Revoked consent blocks upload and chat; events appear in `audit_log`."

## 4. Architecture and Implementation
```
Routes: GET/POST/DELETE /api/v1/patient/consent
  └─► ConsentService(session, patient_id) ──► ConsentRepository(session, patient_id)
                                           └─► AuditRepository (same transaction)
require_consent = get_current_patient + ConsentService.ensure_granted()
```
### 4.1 Key Design Choices
- Notice text and version live in code (`app/core/consent_notice.py`). Consent counts only if it is unrevoked **and** for the current version, so bumping the version forces re-consent.
- Grant must name the current `notice_version` (409 `consent_notice_outdated` otherwise), so a client cannot consent to text the patient did not see.
- A partial unique index allows at most one active consent per patient; concurrent grants resolve to one row.
- Consent change and its audit row commit in one transaction.
- `audit_log` has no FK to `patients` (audit rows outlive the data they describe) and a trigger rejects `UPDATE`/`DELETE`.
- Grant and revoke are idempotent (no duplicate rows or audit events).

## 5. Files and Folders Created or Modified
- `backend/app/core/consent_notice.py`: notice version and text (wording follows spec rules).
- `backend/app/models/consent.py`, `backend/app/models/audit.py`, `backend/app/models/__init__.py`.
- `backend/alembic/versions/0002_consent_and_audit.py`: tables, indexes, append-only trigger.
- `backend/app/repositories/consent_repository.py` (patient-scoped), `backend/app/repositories/audit_repository.py` (append-only).
- `backend/app/services/consent_service.py`, `backend/app/schemas/consent.py`, `backend/app/api/v1/consent.py`, `backend/app/api/v1/router.py`.
- `backend/app/api/deps.py`: `get_consent_service`, `require_consent`.
- `backend/app/core/errors.py`: `ConsentRequiredError` (403), `ConsentNoticeOutdatedError` (409).
- `tests/integration/test_consent.py`, `tests/unit/test_consent_notice.py`, `tests/helpers.py` (`grant_consent`).
- `tests/conftest.py`, `tests/integration/test_auth_security.py`: truncate statements now include `audit_log`/`CASCADE` (required by the new foreign key; no behaviour change).

## 6. Important Classes, Functions and APIs
- `GET /api/v1/patient/consent` → `ConsentStatusRead` (current notice version/text, `granted`, latest grant/revoke timestamps).
- `POST /api/v1/patient/consent` `{notice_version}` → status; 409 if outdated.
- `DELETE /api/v1/patient/consent` → status (idempotent).
- `require_consent` → 403 `consent_required` unless active consent to the current notice.
- All routes: authenticated patient, Origin/`Sec-Fetch-Site` checks, CSRF header on unsafe methods (existing M2 dependencies).

## 7. Database Changes
- **Migration:** `0002_consent_and_audit.py`.
- `consent_records`: `id`, `patient_id` (FK `patients` ON DELETE CASCADE, indexed), `notice_version`, `granted_at`, `revoked_at`; partial unique index `uq_consent_records_one_active` on `patient_id WHERE revoked_at IS NULL`.
- `audit_log`: `id`, `patient_id`, `actor_type` (CHECK patient/doctor/system), `action`, `target_id`, `metadata` (JSONB), `created_at`; index on (`patient_id`, `created_at`); trigger `audit_log_append_only`.
- **RLS:** not yet (M6).

## 8. Security Considerations
- Patient-scoped repository: the consent repository requires `patient_id` at construction; IDs come only from the authenticated session.
- Audit metadata holds notice versions only; no email or document content (test-verified).
- Append-only enforced in the database, not just the application.

## 9. Testing Methodology
Integration tests against PostgreSQL 16 + pgvector and Redis (existing fixtures); a probe route exercises `require_consent` directly because upload (M4) and chat (M7) did not exist yet. Notice version bump simulated with `monkeypatch`.

## 10. Test Cases and Actual Results
| Test File | Test Case Name | Purpose / Scenario Tested | Result |
|---|---|---|---|
| `tests/integration/test_consent.py` | `test_status_before_consent_shows_current_notice` | Default not granted; notice discloses Gemini | **PASSED** |
| | `test_grant_and_revoke_are_audited` | Audit rows, actor, metadata, no PHI | **PASSED** |
| | `test_grant_and_revoke_are_idempotent` | One record, two audit events | **PASSED** |
| | `test_outdated_notice_version_is_rejected` | 409 on stale version | **PASSED** |
| | `test_new_notice_version_requires_fresh_consent` | Version bump forces re-consent; one active row | **PASSED** |
| | `test_consent_is_scoped_to_the_patient` | No cross-patient consent | **PASSED** |
| | `test_consent_routes_require_auth_and_csrf` | 401 / 403 paths | **PASSED** |
| | `test_require_consent_blocks_until_granted_and_after_revoke` | Gate blocks, allows, blocks after revoke | **PASSED** |
| | `test_audit_log_rejects_update_and_delete` | DB trigger enforces append-only | **PASSED** |
| `tests/unit/test_consent_notice.py` | `test_notice_discloses_gemini_and_revocation_with_approved_wording` | Spec wording rules | **PASSED** |
| `tests/integration/test_infrastructure.py` | `test_models_match_migrations`, `test_migrations_downgrade_and_upgrade` | 0002 reversible and in sync | **PASSED** |

The upload half of the acceptance criterion is verified in M4 (`test_upload_requires_active_consent`).

## 11. Problems Encountered and Fixes
1. **Existing tests failed to truncate `patients`:** the new FK from `consent_records` makes plain `TRUNCATE patients` invalid. Added `CASCADE` (and `audit_log`) to the test cleanup statements.

## 12. Verification Results
- **Pytest:** M3-relevant tests 34 passed (full-suite result in the tracker).
- **Linter:** `ruff check .` and `ruff format --check .` clean.
- **Docker Compose:** no Compose changes in M3.

## 13. Limitations and Pending Work
- "Revoking revokes all active shares": share grants do not exist yet; `ConsentService.revoke` is the single hook for M14.
- "Revoked consent blocks chat": chat arrives in M7 and must depend on `require_consent`.
- Auth events (register/login) are not audited; only M3+ events are.

## 14. Final Milestone Status
**`M3: COMPLETED AND VERIFIED`** — consent gate, versioning, and append-only audit are implemented and tested; upload blocking verified with M4.
