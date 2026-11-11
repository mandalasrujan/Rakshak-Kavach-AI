# ADR 0010: Serve the frontend and API on one origin through nginx

- **Status:** Accepted
- **Date:** 2026-11-11

**Context.** Auth relies on httpOnly `SameSite` cookies and an Origin/CSRF check (ADR 0004). Upload size must also be limited before the API spools request bodies (M4 limitation).

**Decision.** The web container (unprivileged nginx) serves the built SPA and proxies `/api` to the API. It sets CSP, `X-Frame-Options`, `Referrer-Policy`, `nosniff` and `Permissions-Policy`. It caps request bodies at 12 MB, overwrites `X-Forwarded-For` with the real client IP, and logs paths without query strings. The Vite proxy is for development only.

**Rejected alternative.** Separate frontend and API origins with CORS and cross-site cookies: weaker cookie protection and more configuration.

**Consequences.** `FRONTEND_ORIGIN` must equal the public origin, `http://localhost:8080` in Compose. TLS and HSTS belong at the edge in front of nginx.
