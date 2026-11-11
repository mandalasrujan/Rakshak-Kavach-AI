# Rakshak Kavach AI — Milestone Tracker

This tracker maintains the verified status of all 18 milestones (M0 through M17) defined in [`PROJECT_SPEC.md`](../PROJECT_SPEC.md). Statuses are updated strictly based on verifiable code, migrations, tests, and runtime evidence.

---

## Overall Progress Summary

| Phase | Milestones | Scope | Status |
|---|---|---|---|
| **Phase 1** | M0 – M2 | Foundation, Architecture, Auth | **COMPLETED & VERIFIED** |
| **Phase 2** | M3 – M5 | Consent, Document Ingestion, Table Extraction | **COMPLETED & VERIFIED** |
| **Phase 3** | M6 – M9 | Isolation, RLS, Embeddings, Baseline RAG, Normalization, Lab Math | **COMPLETED & VERIFIED** (live-Gemini eval pending) |
| **Phase 4** | M10 – M13 | LangGraph Agent, Safety Nodes, Cascading Deletion, Approved Snapshots | NOT STARTED |
| **Phase 5** | M14 – M17 | QR/PIN Scoped Sharing, Dashboard UI, Golden Evals, Load Testing & Polish | NOT STARTED |

---

## Milestone Status Table

| # | Milestone Name | Objective | Status | Verification Status | Report File |
|---|---|---|---|---|---|
| **M0** | Repo & Tooling | Multi-container Compose stack, linters, test harnesses, first 5 ADRs, threat model, synthetic PDF generator | **COMPLETED** | **VERIFIED (Docker + Tests + Ruff)** | [`M0_REPO_AND_TOOLING.md`](M0_REPO_AND_TOOLING.md) |
| **M1** | Backend Skeleton | Layered app (`Router -> Service -> Repository`), config, async Alembic, `/health`, correlation IDs, PHI-redacted JSON logs, CI/CD | **COMPLETED** | **VERIFIED (Docker + Tests + Ruff)** | [`M1_BACKEND_SKELETON.md`](M1_BACKEND_SKELETON.md) |
| **M2** | Authentication | Argon2id password hashing, httpOnly SameSite=Lax JWT cookies, CSRF protection, `/me` profile, Redis token revocation, login rate limits | **COMPLETED** | **VERIFIED (Docker + Tests + Ruff)** | [`M2_AUTHENTICATION.md`](M2_AUTHENTICATION.md) |
| **M3** | Consent and Audit | Versioned consent notice, grant and revoke, `require_consent` dependency, append-only `audit_log` (DB trigger) | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M3_CONSENT_AND_AUDIT.md`](M3_CONSENT_AND_AUDIT.md) |
| **M4** | Upload and Queue | 202 upload, local storage interface, document status, ARQ job with retries and idempotency, magic-byte checks, size/page limits, per-patient dedup | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M4_UPLOAD_AND_QUEUE.md`](M4_UPLOAD_AND_QUEUE.md) |
| **M5** | Table-Aware Extraction | PyMuPDF text + `find_tables`, one record per lab row, narrative chunks with page-level metadata | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M5_TABLE_AWARE_EXTRACTION.md`](M5_TABLE_AWARE_EXTRACTION.md) |
| **M6** | Embeddings & Isolation | `LLMProvider` (Gemini REST + offline fake), pgvector `vector(768)`, non-owner app role, RLS on 5 tables, transaction-scoped `app.patient_id`, patient-scoped vector search | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M6_EMBEDDINGS_AND_ISOLATION.md`](M6_EMBEDDINGS_AND_ISOLATION.md) |
| **M7** | Baseline RAG | `/ask` with page citations, grounding guard, not-found fallback, 20-question eval + long-context baseline harness, minimal React chat | **COMPLETED** | **VERIFIED (Tests + Ruff + native run; offline eval only)** | [`M7_BASELINE_RAG.md`](M7_BASELINE_RAG.md) |
| **M8** | Extraction & Normalization | Deterministic normalization of table rows: 47-test dictionary, unit conversions, numbers, ranges, DD/MM dates, provenance (`lab_results`) | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M8_EXTRACTION_AND_NORMALIZATION.md`](M8_EXTRACTION_AND_NORMALIZATION.md) |
| **M9** | Lab Comparison | Plain-Python previous-vs-latest comparison (improved / worsened / stable / insufficient / not comparable), provenance, `/labs/trends` | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M9_LAB_COMPARISON.md`](M9_LAB_COMPARISON.md) |
| **M10** | LangGraph Agent | LangGraph state graph, 3 structured tools (`search_records`, `get_labs`, `get_medications`), Postgres checkpointer, prompt injection evals | NOT STARTED | Pending Implementation | `M10_AGENT.md` (Planned) |
| **M11** | Safety Nodes | Deterministic red-flag rules with negation window, output guard (diagnostic/prescriptive blocking + numeric consistency check) | NOT STARTED | Pending Implementation | `M11_SAFETY_NODES.md` (Planned) |
| **M12** | Deletion Pipeline | Single cascade service deleting files, database rows, vector chunks, derived labs/meds, and citing chat checkpoints | NOT STARTED | Pending Implementation | `M12_DELETION.md` (Planned) |
| **M13** | Summary Snapshots | Schema-valid doctor summary snapshot built from SQL with optional guard-checked narrative; patient preview and approval flow | NOT STARTED | Pending Implementation | `M13_SUMMARY_SNAPSHOTS.md` (Planned) |
| **M14** | Scoped Sharing | 32-byte hashed token + 6-digit hashed PIN with 5-attempt lockout, scope limits, expiry, session exchange, token stripped from URL | NOT STARTED | Pending Implementation | `M14_SCOPED_SHARING.md` (Planned) |
| **M15** | Dashboard | Five read-only patient dashboard panels (documents, medications, labs with previous comparison, consent, access logs) linking to source pages | NOT STARTED | Pending Implementation | `M15_DASHBOARD.md` (Planned) |
| **M16** | Evals & CI | 25 to 30 golden test cases in CI with mocked LLM; leakage, red-flag, output guard, and retrieval regression tests | NOT STARTED | Pending Implementation | `M16_EVALS_AND_CI.md` (Planned) |
| **M17** | Load Test & Polish | k6 load test run, restart-persistence tests, backup/restore runbook, demo seed data, measured latency and eval numbers in README | NOT STARTED | Pending Implementation | `M17_LOAD_TEST_AND_POLISH.md` (Planned) |

---

## Verification Evidence Log

### Phase 1 Verification (Executed 2026-11-10)
- **Environment:** Windows 11 host with Docker Desktop 29.9.3 (WSL2 engine) + Python 3.12.8.
- **Docker Stack:**
  - `postgres` (`pgvector/pgvector:pg16`): Healthy on `127.0.0.1:5432`.
  - `redis` (`redis:7.4-alpine`): Healthy on `127.0.0.1:6379`.
  - `migrate` (`rakshak-kavach-ai-migrate`): Successfully applied migration `0001_create_patients.py`.
  - `worker` (`rakshak-kavach-ai-worker`): Healthy (running `healthcheck` task interval).
  - `api` (`rakshak-kavach-ai-api`): Healthy on `127.0.0.1:8000`.
- **Health Probing:** `GET http://127.0.0.1:8000/health` returned `200 OK` with database and redis statuses confirmed `ok`.
- **Test Suite Results:**
  - Total Tests: 70
  - Passed: 70
  - Failed: 0
  - Skipped: 0
- **Linting & Code Quality:**
  - `ruff check .`: 0 errors / 0 warnings.
  - `ruff format --check .`: 61 files compliant.


### Phase 2 Verification (Executed 2026-11-10)
- **Environment:** Linux sandbox, Python 3.12, PostgreSQL 16.15 with pgvector 0.6.0, Redis 7.0.15 (native services; Docker Hub was unreachable, so container images were not rebuilt here).
- **Docker Compose:** `docker compose config` valid with the new `storage` volume and worker database settings. Re-run `docker compose up --build --wait` locally to confirm container health.
- **Migrations:** `alembic upgrade head` applied 0002–0004 on the existing Phase 1 database; downgrade/upgrade round trip and model/migration sync verified by tests.
- **End-to-end (native API + `arq` CLI worker):** upload before consent 403; grant 200; upload 202 → `ready` (2 pages); 11 `lab_row` chunks (6 on page 1, 5 on page 2) + 2 narrative chunks; duplicate upload 200; `arq --check` healthy; no names, values or credentials in logs.
- **Test Suite Results:**
  - Total Tests: 125
  - Passed: 125
  - Failed: 0
  - Skipped: 0
- **Linting & Code Quality:**
  - `ruff check .`: 0 errors / 0 warnings.
  - `ruff format --check .`: 96 files compliant.

### Phase 3 Verification (Executed 2026-11-11)
- **Environment:** Linux sandbox, Python 3.12, PostgreSQL 16.15 + pgvector 0.6.0, Redis 7.0.15, Node 22 (native services; Docker Hub unreachable, so container images were not rebuilt here).
- **Docker Compose:** `docker compose config` valid (owner vs app-role URLs, role bootstrap in `migrate`, LLM env). Run `docker compose up --build --wait` locally after adding `APP_DB_USER`/`APP_DB_PASSWORD` (and `LLM_PROVIDER=fake` if no Gemini key) to `.env`.
- **Migrations:** 0004 → 0005 → 0006 → 0007 applied to the existing Phase 2 database; `python -m app.db.app_role` created the non-owner role; full up/down round trip and model/migration sync verified by tests.
- **End-to-end (native API + `arq` worker as non-owner role, `LLM_PROVIDER=fake`):** `/health` ok; 3 uploads → ready; `/ask` hemoglobin → found with page-1 citation; unrelated question → not found; 13 lab results; HbA1c trend `worsened, rising, +0.5 (7.1 → 7.6)`; React app served through Vite proxy (`/patient/me` 200); app role sees 0 rows without context and cannot TRUNCATE; no PHI or secrets in logs.
- **Offline retrieval eval (fake embedder, k=6):** hit rate 0.90 (18/20); answer accuracy RAG 0.85 vs long context 0.85. Live Gemini numbers pending.
- **Test Suite Results:** 241 passed, 0 failed, 0 skipped.
- **Linting & Code Quality:** `ruff check .` clean; `ruff format --check .` 128 files compliant.
