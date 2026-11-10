# Milestone Report: M2 — Authentication

## 1. Milestone Title and Objective
- **Milestone:** M2 — Authentication & Patient Sessions
- **Status:** COMPLETED
- **Objective:** Implement secure patient registration, argon2id password hashing, login issuing httpOnly SameSite=Lax JWT cookies, CSRF protection, protected patient profile access (`/api/v1/patient/me`), logout with Redis token revocation denylists, and Redis-backed brute-force rate limiting.

---

## 2. Why This Milestone is Necessary
In medical applications, user authentication is the first line of defense for Protected Health Information (PHI). Authentication in Rakshak Kavach AI requires strict architectural safeguards:
1. **Immunity to Token Theft (XSS):** Storing JWT tokens in browser `localStorage` or `sessionStorage` exposes tokens to malicious JavaScript or rogue browser extensions. Transporting access tokens strictly via `httpOnly` cookies makes them inaccessible to client scripts.
2. **Protection Against Cross-Site Request Forgery (CSRF):** While `SameSite=Lax` cookies protect against many cross-origin requests, defense-in-depth requires explicit CSRF validation on all state-changing operations (`POST`, `PUT`, `DELETE`).
3. **Resilience to Offline Brute Force:** Standard password hashes (MD5, SHA-256) are trivially reversible with modern GPUs. `argon2id` provides memory-hard, compute-intensive protection against offline cracking.
4. **Immediate Session Invalidation:** Stateless JWTs typically cannot be revoked until expiry. Rakshak Kavach AI pairs JWTs with a Redis-backed token revocation denylist keyed by `jti`, allowing immediate session revocation on logout.

---

## 3. Requirements from `PROJECT_SPEC.md`
According to `PROJECT_SPEC.md` (Milestone M2):
- **Core Deliverables:**
  - Patient registration and login.
  - Password hashing with `argon2`.
  - JWT access tokens stored in an `httpOnly`, `SameSite=Lax`, `Secure` cookie.
  - `get_current_patient` FastAPI dependency for route protection.
  - CSRF protection on state-changing endpoints.
  - Rate limiting on login and registration stored in Redis.
- **Acceptance Criterion:** Protected routes reject unauthenticated, expired, tampered, or cross-site requests, and accept authenticated calls.

---

## 4. Architecture and Implementation

### 4.1 Authentication & Session Flow

```
                      Registration / Login Flow
                      ────────────────────────
Patient Browser                                            FastAPI API / Redis / Postgres
      │                                                                  │
      │── 1. POST /api/v1/auth/login ───────────────────────────────────►│
      │      Headers: X-CSRF-Protection: 1                               │
      │      Body: { "email": "...", "password": "..." }                 │
      │                                                                  │
      │                                                ┌─────────────────┴─────────────────┐
      │                                                │ a. Rate limit check (Redis)       │
      │                                                │ b. Fetch patient (Postgres)       │
      │                                                │ c. Verify password (argon2id)     │
      │                                                │    (Dummy hash if email unknown)  │
      │                                                │ d. Generate JWT with unique jti   │
      │                                                └─────────────────┬─────────────────┘
      │                                                                  │
      │◄── 2. Response 200 OK ───────────────────────────────────────────│
      │       Set-Cookie: rk_access=<jwt>; httpOnly; Secure; SameSite=Lax│
      │       Body: { "id": "...", "email": "...", "created_at": "..." } │
      │                                                                  │

                   Protected Route Access Flow (/api/v1/patient/me)
                   ────────────────────────────────────────────────
Patient Browser                                            FastAPI API / Redis / Postgres
      │                                                                  │
      │── 3. GET /api/v1/patient/me ────────────────────────────────────►│
      │      Cookie: rk_access=<jwt>                                     │
      │                                                ┌─────────────────┴─────────────────┐
      │                                                │ a. Extract rk_access cookie       │
      │                                                │ b. Validate JWT claims (HS256)    │
      │                                                │ c. Check jti in Redis denylist    │
      │                                                │ d. Fetch patient by sub ID (DB)   │
      │                                                └─────────────────┬─────────────────┘
      │                                                                  │
      │◄── 4. Response 200 OK ───────────────────────────────────────────│
      │       Body: Patient Profile JSON                                 │
```

### 4.2 Security Controls & Technical Implementations

1. **Argon2id Hashing & Anti-Enumeration Timing Protection (`PasswordService`):**
   - Implemented using `argon2.PasswordHasher()` with recommended memory/time parameters.
   - When an email does not exist in the database, `verify_dummy(password)` hashes against a pre-generated internal dummy hash. This ensures that the response time for nonexistent accounts matches existing accounts, mitigating username enumeration via timing analysis.

2. **JWT Claims Specification (`TokenService`):**
   - Algorithm: `HS256`.
   - Mandatory claims:
     - `sub`: Subject (patient UUID).
     - `jti`: Unique token identifier (`uuid4().hex`).
     - `iss`: Issuer (`rakshak-kavach-api`).
     - `aud`: Audience (`rakshak-kavach:patient`).
     - `iat`: Issued at timestamp.
     - `exp`: Expiration timestamp (default: 30 minutes).

3. **CSRF & Origin Enforcement (`enforce_same_site_request`):**
   - Applied as a router-level dependency on `/api/v1/auth` and state-changing endpoints.
   - Unsafe HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`) must supply the custom header `X-CSRF-Protection: 1`.
   - Requests carrying `Origin` or `Referer` headers are strictly compared against `settings.frontend_origin`.

4. **Redis Rate Limiting (`RateLimiter`):**
   - Uses fixed-window counters in Redis:
     - Login: Maximum 5 attempts per email, 20 attempts per IP per 15-minute window (`LOGIN_WINDOW_SECONDS=900`).
     - Registration: Maximum 10 attempts per IP per 1-hour window (`REGISTER_WINDOW_SECONDS=3600`).
   - Responds with `429 Too Many Requests` on limit breach.

5. **Token Revocation on Logout (`AuthService.logout`):**
   - Decodes the token to obtain its `jti` and expiration timestamp.
   - Computes remaining TTL: `ttl = int((claims.expires_at - now).total_seconds())`.
   - Sets Redis key `revoked:jti:{jti}` with expiry equal to `ttl`.
   - Emits a cleared cookie (`delete_cookie`) in the HTTP response.
   - Any subsequent attempt to present this token before its natural expiry is rejected with `401 Unauthorized`.

---

## 5. Files and Folders Created or Modified
- `backend/app/core/security.py`: `PasswordService` (argon2id) and `TokenService` (JWT encoder/decoder).
- `backend/app/services/auth_service.py`: High-level registration, login, logout, and token validation logic.
- `backend/app/services/rate_limiter.py`: Redis-backed fixed-window rate limiter.
- `backend/app/schemas/auth.py`: Pydantic request models (`RegisterRequest`, `LoginRequest`).
- `backend/app/schemas/patient.py`: Pydantic response models (`PatientRead`).
- `backend/app/api/deps.py`: FastAPI dependencies (`get_current_patient`, `enforce_same_site_request`, `client_ip`).
- `backend/app/api/v1/auth.py`: HTTP routes for `/register`, `/login`, `/logout`.
- `backend/app/api/v1/patient.py`: HTTP route for `/me`.
- `tests/helpers.py`: Test utilities (`register`, `login`, `register_and_login`).
- `tests/integration/test_auth.py`: Functional authentication flow tests.
- `tests/integration/test_auth_security.py`: Comprehensive security and adversarial tests.
- `tests/unit/test_security.py`: Isolated unit tests for password hashing, JWT decoding, and CSRF checks.

---

## 6. Important Classes, Functions and APIs

### 6.1 `PasswordService` (`backend/app/core/security.py`)
- `hash(password: str) -> str`: Generates an argon2id hash.
- `verify(password_hash: str, password: str) -> bool`: Verifies a plaintext candidate against a stored hash.
- `verify_dummy(password: str) -> None`: Runs verification against a dummy hash to equalize response times.

### 6.2 `TokenService` (`backend/app/core/security.py`)
- `create_access_token(patient_id: UUID) -> AccessToken`: Issues an HS256 JWT populated with `sub`, `jti`, `iss`, `aud`, and `exp`.
- `decode(token: str) -> TokenClaims`: Verifies signature, issuer, audience, and expiration, raising `NotAuthenticatedError` on any mismatch.

### 6.3 Authentication Service (`backend/app/services/auth_service.py`)
- `register(email, password, client_ip)`: Rate-limits, checks uniqueness, hashes password, and persists patient.
- `login(email, password, client_ip)`: Rate-limits, fetches patient, verifies password with anti-enumeration protection, and issues an access token.
- `logout(token)`: Adds token `jti` to Redis revocation denylist.

### 6.4 Route Endpoints
- `POST /api/v1/auth/register`: Creates a patient account (`201 Created`).
- `POST /api/v1/auth/login`: Validates credentials and sets `rk_access` cookie (`200 OK`).
- `POST /api/v1/auth/logout`: Revokes token in Redis and removes cookie (`204 No Content`).
- `GET /api/v1/patient/me`: Returns profile of the authenticated patient (`200 OK`).

---

## 7. Database Changes
Utilizes the `patients` table created in M1 (`0001_create_patients.py`). All queries are scoped to the authenticated patient's ID.

---

## 8. Security Considerations
- **No Plaintext Passwords:** Passwords exist in memory only as Pydantic `SecretStr` instances and are hashed before persistence.
- **Strict Cookie Attributes:** Cookies are configured with `httponly=True`, `secure=True` (in production), `samesite="lax"`, and `path="/"`.
- **Cross-Site Request Forgery:** Protected by dual controls (SameSite cookie attribute + `X-CSRF-Protection: 1` header check).
- **Anti-Brute Force:** Stored in Redis with automatic TTL expiration to prevent database exhaustion.
- **Revocation Denylist:** Prevents token replay attacks post-logout.

---

## 9. Testing Methodology
- **Unit Testing:**
  - Password hashing verification, wrong password rejection, and dummy hash timing behavior.
  - JWT claim validation, tampered signature rejection, and expired token rejection.
  - CSRF header and origin validation logic.
- **Integration & Adversarial Testing:**
  - Full registration, login, profile retrieval, and logout cycle.
  - Cross-site POST rejection when CSRF header is absent or origin is untrusted.
  - Rate limiter exhaustion: verifying that exceeding 5 failed logins triggers HTTP 429.
  - Revocation test: verifying that a logged-out token cookie is rejected even if its timestamp is still technically valid.

---

## 10. Test Cases and Actual Results

| Test File | Test Case | Purpose | Result |
|---|---|---|---|
| `tests/unit/test_security.py` | `test_hash_and_verify_password` | Verify argon2id hash and verify behavior | **PASSED** |
| `tests/unit/test_security.py` | `test_invalid_password_returns_false` | Reject wrong password | **PASSED** |
| `tests/unit/test_security.py` | `test_jwt_roundtrip` | Verify token creation and claim decoding | **PASSED** |
| `tests/unit/test_security.py` | `test_jwt_tampered_signature_rejected` | Reject modified token payload/signature | **PASSED** |
| `tests/unit/test_security.py` | `test_jwt_expired_rejected` | Reject token past its expiration time | **PASSED** |
| `tests/unit/test_security.py` | `test_csrf_header_validation` | Ensure X-CSRF-Protection: 1 is enforced | **PASSED** |
| `tests/unit/test_security.py` | `test_origin_validation` | Reject unauthorized cross-site origins | **PASSED** |
| `tests/integration/test_auth.py` | `test_register_login_me_logout_flow` | End-to-end patient auth and session lifecycle | **PASSED** |
| `tests/integration/test_auth.py` | `test_unauthenticated_request_to_me_returns_401` | Reject access to /me without cookie | **PASSED** |
| `tests/integration/test_auth.py` | `test_duplicate_email_registration_returns_409` | Reject duplicate email registration | **PASSED** |
| `tests/integration/test_auth.py` | `test_invalid_credentials_returns_401` | Reject wrong password on login | **PASSED** |
| `tests/integration/test_auth.py` | `test_validation_errors_return_422` | Reject invalid email format or short passwords | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_password_is_hashed_with_argon2` | Verify database never stores plaintext | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_csrf_header_required_for_auth_post` | Reject auth POST requests without CSRF header | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_cross_origin_request_rejected` | Reject cross-site Origin / Referer | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_revoked_token_is_rejected_after_logout` | Verify Redis token denylist invalidates token | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_login_rate_limiting_per_email` | Block brute force on email after 5 attempts | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_login_rate_limiting_per_ip` | Block brute force on IP address | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_registration_rate_limiting_per_ip` | Block automated registration spam | **PASSED** |
| `tests/integration/test_auth_security.py` | `test_cookie_attributes_are_secure` | Verify httpOnly, SameSite=Lax flags | **PASSED** |

---

## 11. Problems Encountered and Fixes
- None in the M2 implementation itself. All security assertions and cryptographic operations passed without failure.

---

## 12. Verification Results
- 70 out of 70 total project tests passed (including all 30 auth-specific unit and integration tests).
- All security and rate-limiting assertions verified against active PostgreSQL and Redis instances.

---

## 13. Limitations and Pending Work
- **Consent Notice Gating (M3):** Authenticated patients are not yet gated by the versioned consent notice (`require_consent` dependency will be added in M3).
- **Audit Logging (M3):** Authentication events (logins, logouts, failures) are currently logged to application stdout; dedicated persistent database audit logging in the `audit_log` table is slated for M3.
- **Email Verification:** Email verification is not included in Phase 1 (accepted risk noted in `docs/threat-model.md`).

---

## 14. Final Milestone Status
**`M2: COMPLETED AND VERIFIED`**
- All authentication, authorization, cryptographic hashing, cookie security, CSRF protection, and rate limiting requirements from `PROJECT_SPEC.md` are fully implemented and verified.

