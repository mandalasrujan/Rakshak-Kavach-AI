# Milestone Report: M14 — Doctor Scoped Sharing (security-critical)

## Objective
Patient-initiated, read-only, time-limited doctor access to one approved snapshot, via a QR code plus a PIN.

- **Spec "done when":** expired or revoked → 401; 5 wrong PINs lock the share; scope limits the data; the token is absent from the final URL.

## Implementation
**Patient side** (`/api/v1/patient/shares`; auth, same-site/CSRF):
- `POST` (consent required): accepts only the patient's own approved, valid snapshot, with a scope (`summary_only` or `full_records`) and an expiry of 10 to 1,440 minutes (`SHARE_MAX_EXPIRY_MINUTES`).
  - Returns the token, the 6-digit PIN and `share_url = {FRONTEND_ORIGIN}/share#t=<token>` **once**, with `Cache-Control: no-store`.
  - Stores only `sha256(token)` and an argon2id PIN hash.
- `GET`: lists shares with status (`active` / `expired` / `revoked` / `locked`), failed attempts, and an access log (sessions with self-declared name and registration number, view counts).
- `DELETE /{id}`: revokes immediately.

**Doctor side** (`/api/v1/share`; Origin/CSRF checked; no patient dependencies):
- `POST /sessions {token, pin, declared_name?, declared_reg_no?}`:
  - per-IP rate limit (20 per 15 minutes);
  - `share_grant_owner()` (SECURITY DEFINER) maps the token hash to its owner, then the RLS context is set;
  - the grant is row-locked; any non-active grant gets a generic 401 `share_unavailable`;
  - a wrong PIN increments the counter (401 `invalid_pin`); the 5th failure locks the share permanently;
  - a correct PIN creates a session: a 32-byte random token stored hashed, expiring at `min(now + 30 min, share expiry)`, in an httpOnly, `Secure`, `SameSite=Strict` cookie with `Path=/api/v1/share`.
- `GET /view`: requires an active session and an active, unlocked, unexpired share whose snapshot is approved and valid. It returns the **frozen approved snapshot**, cut by scope:
  - `summary_only` drops the document list and all sources;
  - `full_records` includes sources and excerpts.
- `POST /session/end`: ends the session (idempotent).

**Cascades:**
- Revoking consent revokes all active shares (M3 hook).
- Deleting a source document revokes shares of invalidated snapshots (M12 hook).

**Audit (PHI-free):**
- Events: `share.created`, `share.pin_failed` (with the attempt number), `share.locked`, `share.access_denied` (with a reason), `share.session_started`, `share.viewed`, `share.revoked`.
- Doctor names are kept only in `doctor_sessions`, never in audit metadata or logs.

**Headers:** `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY` on all API responses.

**Frontend:** the token is read from the fragment and removed from the address bar immediately (`history.replaceState`); it is held in memory only.

## Files
- **New:** `backend/app/models/share.py`, `backend/app/schemas/share.py`, `backend/app/repositories/share_repository.py`, `backend/app/services/share_service.py`, `backend/app/services/share_access.py`, `backend/app/api/v1/shares.py`, `backend/app/api/v1/share.py`, migration `0011_doctor_sharing.py`, `tests/integration/test_sharing.py`, `docs/adr/0008-doctor-share-access.md`.
- **Modified:**
  - `core/config.py` (share settings, `SHARE_COOKIE_NAME`), `core/errors.py` (`share_unavailable`, `invalid_pin`), `core/request_context.py` (headers).
  - `services/consent_service.py`, `services/document_deletion.py` (cascades).
  - `api/deps.py`, `api/v1/router.py`, `models/__init__.py`.
  - Assertions in two existing tests for the new audit keys.

## Database (0011)
- `share_grants`: spec columns plus `snapshot_id`, `created_at`, `locked_at`; unique `token_hash`; CHECK on scope.
- `doctor_sessions`: spec columns plus `patient_id`, `token_hash` (unique), `created_at`, `ended_at`.
- Both tables have RLS `patient_isolation` and grants SELECT, INSERT and UPDATE (no DELETE).
- Functions `share_grant_owner(text)` and `doctor_session_owner(text)` are `SECURITY DEFINER` with a fixed `search_path`, `REVOKE ALL FROM PUBLIC`, and `GRANT EXECUTE` to `rakshak_app` only.

## Security tests (19, all passed)
| Test | Result |
|---|---|
| Creation requires an approved snapshot, a valid scope, the maximum expiry, CSRF and consent | **PASSED** |
| Token and PIN shown once; DB holds SHA-256 and argon2id only; URL uses the fragment; not in the list response | **PASSED** |
| Correct PIN → 30-minute session; cookie flags and path; `no-referrer`; read-only (POST/PUT/PATCH/DELETE on view → 405); access log shows name and views | **PASSED** |
| Session never outlives a 10-minute share | **PASSED** |
| **5 wrong PINs lock permanently**; the correct PIN is then refused; an existing session dies with the lock; 5 `pin_failed` events plus `locked` audited | **PASSED** |
| Expired share, revoked share, timed-out session, and ended session with **replayed old cookie** → 401 (4 cases) | **PASSED** |
| Unknown or tampered token → generic 401; malformed PIN → 422 without echo; forged session cookie → 401; foreign Origin → 403 | **PASSED** |
| Token reuse needs the PIN each time; both sessions die on revoke; each exchange audited | **PASSED** |
| **Scope enforced:** `summary_only` has no documents or sources anywhere; `full_records` has both | **PASSED** |
| Doctor sees only the approved version (v1) after a newer draft exists | **PASSED** |
| Doctor session cannot reach any patient API, even if the cookie is sent everywhere or presented as `rk_access` (401 on 6 endpoints + DELETE) | **PASSED** |
| Cross-patient: B cannot list, revoke or share A's data; A's view contains no B data; no rows visible without RLS context | **PASSED** |
| Consent revocation and document deletion revoke shares and kill sessions | **PASSED** |
| PIN exchange rate-limited per IP (4th → 429) | **PASSED** |
| Token, PIN, session token, PHI and doctor name absent from logs and audit metadata | **PASSED** |
| Doctor modules import no patient services or patient dependencies (AST check) | **PASSED** |

**Mutation checks** (to prove the tests can fail): disabling the lockout made the lock test fail, and keeping the document list in `summary_only` made the scope test fail. Both changes were reverted.

## Known limitations
- Doctor identity is self-declared and unverified.
- The QR code and PIN together are a bearer credential until expiry; revoking the share is the response to a leak.
- No device binding.
- Real browser QR scanning was not tested here; the share page is covered by component tests.

## Status
**`M14: COMPLETED AND VERIFIED`**
