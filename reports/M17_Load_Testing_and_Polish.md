# Milestone Report: M17 — Load Testing and Polish

## Objective
Repeatable load tests with real measurements, a restart-persistence test, a backup and restore drill, a production configuration review, frontend polish, a seeded demo patient, and a final technical verification.

- **Spec "done when":** real p50/p95 latency recorded; the demo runs from a fresh deploy.
- **Performance targets:** the spec sets none, so measurements are reported without pass/fail latency thresholds. Error rate is gated at below 1% per workflow.

## Load test (k6 v0.54.0, `loadtest/rakshak.js`)
**Environment:** 1 vCPU and 4 GB RAM shared by k6, the API (1 uvicorn worker), the ARQ worker, PostgreSQL 16 and Redis 7, run natively. Fake LLM. Disposable database. Load-test rate limits.

| Workflow | VUs | Requests | Req/s | p50 ms | p95 ms | p99 ms | Max ms | Errors |
|---|---|---|---|---|---|---|---|---|
| Reads (documents, labs, trends, medications) | 4 | 6,252 | 208.4 | 17.8 | 24.3 | 36.8 | 860.6 | 0 |
| Ask (agent graph, fake LLM) | 3 | 1,590 | 53.0 | 51.8 | 79.6 | 148.8 | 634.2 | 0 |
| Login (argon2id) | 2 | 152 | 5.1 | 391.4 | 449.6 | 508.9 | 571.9 | 0 |
| Upload (+ status polls) | 1 | 291 | 9.7 | 7.4 | 14.5 | 23.4 | 190.3 | 0 |
| Doctor share view | 2 | 4,738 | 157.9 | 11.5 | 17.6 | 25.7 | 394.7 | 0 |

- **Document processing**, upload to `ready`: 72 documents; p50 526 ms, p95 656 ms, p99 795 ms; 0 failures.
- **Totals:** 13,102 requests, 0 failed; 14,456 checks, 0 failed.
- **Resources:** API CPU 59.7% average (72.4% max), RSS 281 MB max; worker 3.5% (16.7%), 128 MB; PostgreSQL 4.4% (7.4%), 262 MB; Redis 0.2%, 10 MB.

**Bottleneck review:**
- **Login** (about 390 ms p50) is argon2id's deliberate cost (64 MiB, t=3), run off the event loop. It is kept as a security trade-off.
- **`/ask`** spends 3.9 ms of its about 52 ms p50 building and compiling the LangGraph graph per request. Caching it would mean restructuring how per-request dependencies reach the nodes, for about 8%, so it is not done.
- No database pool exhaustion, timeouts or errors at this load.
- The max-latency spikes (0.4 to 0.9 s) coincide with phase transitions on a single shared core.

**Harness bugs found and fixed (not app bugs):**
- k6 never sends `Secure` cookies over http; local runs need the development-only `COOKIE_SECURE=false`.
- k6 resets cookies every iteration; fixed with `noCookiesReset`.
- Init-context values differ per VU, so user emails now come from `setup()`.

## Restart persistence (verified)
1. A document was queued with the worker stopped.
2. PostgreSQL and Redis (append-only file) were both restarted.
3. Login, consent, documents and the queued job all survived, and the worker then processed the document to `ready` with 3 lab results.

## Backup and restore drill (verified)
`pg_dump -Fc` (216 KB), then `pg_restore` into a new database. Row counts matched for all 11 tables checked (including 68 vectors and 4,961 audit rows). All 13 RLS policies and the audit trigger were present. Procedure: `docs/operations.md`.

## Production configuration review and changes
- **Frontend container** (`frontend/Dockerfile`: Node build, then unprivileged nginx 1.27). nginx serves the SPA on the same origin as `/api` (ADR 0010) and adds:
  - CSP (`default-src 'self'`, `frame-ancestors 'none'`), `X-Frame-Options DENY`, `Referrer-Policy no-referrer`, `nosniff`, `Permissions-Policy`;
  - `client_max_body_size 12m`, which fixes the M4 limitation of no proxy body limit;
  - `X-Forwarded-For` **overwritten** with the client IP;
  - access logs that record method and path only.
- **Compose:** new `web` service on `127.0.0.1:8080`. The API gets `FORWARDED_ALLOW_IPS` and `WEB_CONCURRENCY` (default 2). `FRONTEND_ORIGIN` now defaults to `http://localhost:8080`.
- **API:** `X-Frame-Options: DENY` added alongside `nosniff`, `Referrer-Policy` and `Cache-Control: no-store`.
- **Verified with nginx 1.24** (the production config, with the upstream pointed at the native API):
  - `nginx -t` OK; `/health` returns ok; the SPA and its fallback return 200; all headers present;
  - `/api` proxied (401 on a protected route);
  - spoofed `X-Forwarded-For` values still hit the per-IP login limit (3rd attempt → 429);
  - a 13 MB upload → 413;
  - access log shows the path only.
- **Reviewed without changes:**
  - CORS allows only the frontend origin.
  - CSRF and Origin checks are on all patient, share and auth routers.
  - Rate limits: login, registration, ask/chat, share exchange.
  - PHI-free logging is test-enforced.
  - Secrets come from the environment only; placeholders and short JWT secrets are refused; `COOKIE_SECURE=false` and the fake LLM are refused in production.
  - Containers run as non-root with healthchecks and `restart: unless-stopped`.

## Frontend accessibility
- axe-core has 0 violations on the login page, the doctor PIN page, and answers with citations (3 tests).
- Labelled inputs, focus rings, `aria-live` chat, alert/status roles.
- Mobile layouts stack below `md`, and tables scroll horizontally.

## Seeded demo patient
`scripts/seed_demo.py` drives the public API: register, consent, upload the 10 synthetic "Asha" reports, wait for processing, then generate and approve a summary. Run against the live native stack: "10/10 documents processed, summary v1 approved".

## Files
- **New:**
  - Load test: `loadtest/{rakshak.js,sample_resources.sh,README.md}`.
  - Frontend container: `frontend/{Dockerfile,nginx.conf}`, `frontend/src/__tests__/a11y.test.jsx`.
  - `scripts/seed_demo.py`.
  - Docs: `docs/operations.md`, `docs/adr/0008`–`0010`, `reports/FINAL_TECHNICAL_VERIFICATION.md`.
- **Modified:** `docker-compose.yml`, `.env.example`, `.dockerignore`, `.github/workflows/ci.yml` (web smoke tests), `backend/app/core/request_context.py`, `docs/{deployment,threat-model}.md`, `README.md`.

## Not performed here
- **Docker images:** not built or run (Docker Hub is unreachable from this sandbox); the CI `compose` job covers it.
- **Tracing:** no tracing screenshot. Langfuse (named in the spec's tech stack) was **not integrated**; per-node latency logs are the only tracing.
- **Gemini latency:** not measured.

## Status
**`M17: COMPLETED`**
- Load test, persistence, backup and restore, configuration and demo are verified natively.
- Container build and tracing are outstanding (see above).
