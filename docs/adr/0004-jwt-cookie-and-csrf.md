# ADR 0004: JWT in an httpOnly cookie with CSRF header check

- **Status:** Accepted
- **Date:** 2026-11-10

**Context.** The React app must authenticate patients without exposing tokens to JavaScript (XSS) while staying protected against cross-site request forgery.

**Decision.** Short-lived HS256 JWT (default 30 min; `sub`, `jti`, `iss`, `aud`, `iat`, `exp` required) in an `httpOnly`, `Secure`, `SameSite=Lax` cookie. Logout adds the `jti` to a Redis denylist until expiry; token checks fail closed if Redis is down. Patient and auth routes reject any request whose `Origin` is not the configured frontend origin or whose `Sec-Fetch-Site` is `cross-site`; unsafe methods also require `X-CSRF-Protection: 1` (custom headers cannot be sent cross-site without a CORS preflight, which is only allowed for the frontend origin).

**Rejected alternative.** Token in `localStorage` with an `Authorization` header: readable by any injected script. Synchronizer CSRF tokens: more state for no gain given SameSite plus custom-header checks.

**Consequences.** Frontend and API must be served same-site in production. `COOKIE_SECURE=false` exists only for local plain-http testing and is rejected in production.
