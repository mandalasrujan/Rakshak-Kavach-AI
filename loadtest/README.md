# Load testing (M17)

`rakshak.js` is a [k6](https://k6.io) script. It runs five timed phases one after another, so each workflow is measured on its own:

| Phase | VUs | What each iteration does |
|---|---|---|
| reads | `USERS` | `GET` documents, labs, trends, medications |
| ask | 3 | `POST /patient/ask` (agent graph; the LLM provider is whatever the API runs) |
| login | 2 | `POST /auth/login` (argon2id verification) |
| upload | 1 | upload a PDF (unique bytes) → poll until `ready` → `DELETE` it |
| share | 2 | doctor PIN exchange once, then `GET /share/view` |

`setup()` registers synthetic users, grants consent, uploads three synthetic reports per user, waits for processing, and approves a snapshot and a share for each user.

## Running it

The API must be started with **load-test settings in a disposable database**:

- Raise the rate limits: `LOGIN_MAX_ATTEMPTS_PER_IP`, `LOGIN_MAX_ATTEMPTS_PER_EMAIL`, `REGISTER_MAX_ATTEMPTS_PER_IP`, `ASK_MAX_PER_HOUR` and `SHARE_EXCHANGE_MAX_PER_IP` (for example `1000000`). With production limits, a single load-generating IP is correctly answered with 429.
- Use `LLM_PROVIDER=fake` unless you want to measure Gemini latency (and pay for the calls).
- Over plain `http://`, use the development-only `COOKIE_SECURE=false`, because k6 never sends `Secure` cookies over http, not even to localhost. It is rejected when `APP_ENV=production`.

```bash
python scripts/generate_synthetic_pdfs.py --out data/synthetic
loadtest/sample_resources.sh > load-results/resources.csv &   # optional CPU/RSS sampling
cd loadtest && k6 run -e BASE_URL=http://127.0.0.1:8000 -e USERS=4 -e PHASE_SECONDS=30 \
  -e SYNTHETIC_DIR=../data/synthetic -e SUMMARY_FILE=../load-results/k6-summary.json rakshak.js
```

The script fails if any phase has an error rate of 1% or more. Latency is reported, not gated, because the spec sets no latency targets.

## Measured run (2026-11-11)

- **Environment:** 1 vCPU and 4 GB RAM shared by k6, the API (1 uvicorn worker), the ARQ worker, PostgreSQL 16 and Redis 7, all native processes. `LLM_PROVIDER=fake`, so `/ask` latency excludes any real model call.

| Workflow | VUs | Requests | Req/s | p50 ms | p95 ms | p99 ms | Max ms | Errors |
|---|---|---|---|---|---|---|---|---|
| reads | 4 | 6,252 | 208.4 | 17.8 | 24.3 | 36.8 | 860.6 | 0 |
| ask (agent, fake LLM) | 3 | 1,590 | 53.0 | 51.8 | 79.6 | 148.8 | 634.2 | 0 |
| login (argon2id) | 2 | 152 | 5.1 | 391.4 | 449.6 | 508.9 | 571.9 | 0 |
| upload (+ status polls) | 1 | 291 | 9.7 | 7.4 | 14.5 | 23.4 | 190.3 | 0 |
| share (doctor view) | 2 | 4,738 | 157.9 | 11.5 | 17.6 | 25.7 | 394.7 | 0 |

- **Document processing**, from upload to `ready` (validate, extract, embed, normalise): 72 documents; p50 526 ms, p95 656 ms, p99 795 ms; 0 failures.
- **Totals:** 13,102 requests, 0 failed; 14,456 checks passed, 0 failed.

Resources, sampled every 2 s:

| Process | CPU avg | CPU max | RSS max |
|---|---|---|---|
| API (uvicorn) | 59.7% | 72.4% | 281 MB |
| ARQ worker | 3.5% | 16.7% | 128 MB |
| PostgreSQL | 4.4% | 7.4% | 262 MB |
| Redis | 0.2% | 0.2% | 10 MB |

These numbers come from one machine with every component competing for a single core. They are a baseline for regressions, not a capacity claim.
