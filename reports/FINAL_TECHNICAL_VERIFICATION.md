# Final Technical Verification — Rakshak Kavach AI v1 (M0–M17)

**Date:** 2026-11-11

**Commit range:** `b996963` (initial setup) … Phase 5 head

**Environment:** Linux sandbox, 1 vCPU / 4 GB RAM, Python 3.12, PostgreSQL 16.15 + pgvector 0.6.0, Redis 7.0.15, Node 22, k6 0.54.0, nginx 1.24. Services ran natively because Docker Hub was unreachable. No Gemini API access; all LLM-dependent runs used the deterministic offline provider.

## 1. Results summary
| Check | Result |
|---|---|
| Backend tests (`pytest`, M0–M17) | **321 passed, 0 failed, 0 skipped** |
| Frontend tests (Vitest, incl. axe) | **13 passed, 0 failed** |
| Frontend production build | passes |
| Ruff lint / format | clean / 177 files compliant |
| GitHub workflow lint (`actionlint`) | no findings |
| Alembic | fresh upgrade to 0011, `alembic check` no drift, full downgrade/upgrade |
| Docker Compose config | valid (postgres, redis, migrate, api, worker, web) |
| Docker image build / `compose up` | **not run here** (registry unreachable); covered by the CI `compose` job |
| GitHub Actions run | **not run here** (no repository access) |
| Secret scan | clean |
| Live Gemini evaluation | **not run** (no key or network access); `live-eval.yml` provided |

## 2. Security verification
- **Patient isolation:**
  - Non-owner app role with RLS on all 13 patient tables and transaction-scoped `app.patient_id`.
  - Leakage tests at the repository and RLS layers (M6, M10, M13, M14).
  - Golden eval: 0 cross-patient citations.
- **Auth and CSRF:** argon2id, httpOnly cookies, Origin and `Sec-Fetch-Site` checks, CSRF header on unsafe methods. The frontend client adds it automatically (test-enforced).
- **Doctor sharing (M14):** 19 security tests covering PIN lockout, expiry, revocation, timeout, replay, scope, cross-patient access, patient-API isolation, rate limits, and log/audit hygiene, plus 2 mutation checks proving the tests fail on regressions.
- **Safety (M11):** deterministic red flags (urgent guidance cannot be overridden), injection input guard, and a no-diagnosis plus numeric-consistency output guard, applied to chat and to the snapshot narrative.
- **Deletion (M12/M13/M14):** retry-safe cascade; invalidates snapshots and revokes shares; workers cannot recreate deleted data.
- **Headers:**
  - API: `nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store`.
  - nginx: adds CSP, `Permissions-Policy`, a 12 MB body limit, an anti-spoof `X-Forwarded-For`, and query-free access logs.
- **Secrets:** environment only; placeholder or short secrets are refused; `COOKIE_SECURE=false` and the fake LLM are refused in production; `.env` is excluded from the repository and the package.

## 3. Evaluation (deterministic offline provider; not Gemini quality)
- Golden eval (26 cases): answers 0.75, not-found 1.0, isolation 1.0, red flags 1.0, injection 1.0, cross-patient and ungrounded citations 0.
- Retrieval hit@6 0.90.
- Tool selection 10/10.
- Safety eval: recall 22/22, precision 1.0, injection 8/8, guard 12/12 with 0/10 false blocks (in-sample).
- Lab extraction precision and recall 1.0 on 30 rows.

## 4. Performance (k6; 1 vCPU shared by all components; fake LLM)
| Workflow | p50 | p95 | p99 | Req/s | Errors |
|---|---|---|---|---|---|
| Reads | 17.8 ms | 24.3 ms | 36.8 ms | 208.4 | 0 |
| Ask (agent) | 51.8 ms | 79.6 ms | 148.8 ms | 53.0 | 0 |
| Login (argon2id) | 391.4 ms | 449.6 ms | 508.9 ms | 5.1 | 0 |
| Upload | 7.4 ms | 14.5 ms | 23.4 ms | 9.7 | 0 |
| Doctor view | 11.5 ms | 17.6 ms | 25.7 ms | 157.9 | 0 |
| Processing (upload → ready) | 526 ms | 656 ms | 795 ms | — | 0 |

## 5. Operations
- **Restart persistence:** a queued job survived Redis (append-only file) and PostgreSQL restarts and was processed afterwards.
- **Backup and restore:** all checked tables and RLS policies matched after `pg_restore`.
- **Demo seed:** a fresh synthetic patient with 10/10 documents processed and an approved summary.

## 6. Outstanding items (honest list)
1. Build and run the Docker images (`docker compose up --build --wait`) and get the first green GitHub Actions run, on a machine with registry access.
2. Live Gemini evaluation: configure the secrets and run `live-eval.yml`; tune `RAG_MIN_SIMILARITY` for Gemini embeddings.
3. Langfuse tracing with masking (named in the spec's tech stack) is not integrated, so there is no tracing screenshot. Per-node latency logs exist.
4. No end-to-end browser tests; colour contrast was not machine-checked.
5. Clinician review of red-flag rules, encryption at rest, backup encryption and a formal compliance review are needed before any real patient use. Data handling is modeled on DPDP principles; this is not a compliance claim.
