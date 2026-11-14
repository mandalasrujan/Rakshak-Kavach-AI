# Rakshak Kavach AI — Milestone Tracker

This tracker maintains the verified status of all 18 milestones (M0 through M17) defined in [`PROJECT_SPEC.md`](../PROJECT_SPEC.md). Statuses are updated strictly based on verifiable code, migrations, tests, and runtime evidence.

---

## Overall Progress Summary

| Phase | Milestones | Scope | Status |
|---|---|---|---|
| **Phase 1** | M0 – M2 | Foundation, Architecture, Auth | **COMPLETED & VERIFIED** |
| **Phase 2** | M3 – M5 | Consent, Document Ingestion, Table Extraction | **COMPLETED & VERIFIED** |
| **Phase 3** | M6 – M9 | Isolation, RLS, Embeddings, Baseline RAG, Normalization, Lab Math | **COMPLETED & VERIFIED** (live-Gemini eval pending) |
| **Phase 4** | M10 – M12 | LangGraph Agent, Safety Nodes, Cascading Deletion | **COMPLETED & VERIFIED** (live-Gemini eval pending) |
| **Phase 5** | M13 – M17 | Snapshots, QR/PIN Scoped Sharing, Dashboard UI, Golden Evals & CI, Load Testing & Polish | **COMPLETED & VERIFIED** (all blockers resolved; live-Gemini eval pending) |

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
| **M10** | LangGraph Agent | LangGraph graph (consent → red flags → input guard → deterministic tools → answer → output guard), tools `search_records` / `get_labs` / `get_medications`, RLS-backed checkpointer, chats, 10/10 tool selection | **COMPLETED** | **VERIFIED (Tests + Ruff + native run; offline provider)** | [`M10_LANGGRAPH_MEDICAL_HISTORY_AGENT.md`](M10_LANGGRAPH_MEDICAL_HISTORY_AGENT.md) |
| **M11** | Safety Nodes | Versioned YAML red flags with negation/history (recall 1.0, precision 1.0 on in-sample set), injection input guard, no-diagnosis + numeric output guard, urgent cannot be overridden | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M11_SAFETY_NODES_AND_GUARDRAILS.md`](M11_SAFETY_NODES_AND_GUARDRAILS.md) |
| **M12** | Deletion Pipeline | Retry-safe cascade deleting file, chunks/embeddings, labs, medications, citing chats + checkpoints; row lock stops workers recreating data | **COMPLETED** | **VERIFIED (Tests + Ruff + native run)** | [`M12_SECURE_PATIENT_DATA_DELETION.md`](M12_SECURE_PATIENT_DATA_DELETION.md) |
| **M13** | Summary Snapshots | Versioned snapshots; medications/labs/documents from SQL with page provenance; guarded AI narrative; approve-once immutability; invalidation + purge on source deletion | **COMPLETED** | **VERIFIED (11 tests + Ruff)** | [`M13_Summary_Snapshots.md`](M13_Summary_Snapshots.md) |
| **M14** | Scoped Sharing | SHA-256 token in URL fragment + argon2id PIN, 5-attempt permanent lock, 30-min path-scoped session, scope-limited frozen snapshot, revocation cascades, RLS via SECURITY DEFINER owner lookup | **COMPLETED** | **VERIFIED (19 security tests + 2 mutation checks)** | [`M14_Doctor_Scoped_Sharing.md`](M14_Doctor_Scoped_Sharing.md) |
| **M15** | Dashboard | React + Tailwind dashboard (records, assistant, labs, medications, summary, sharing, consent) + doctor share page; every value links to its source PDF page | **COMPLETED** | **VERIFIED (13 frontend tests incl. axe, build, 1 backend test)** | [`M15_Patient_Dashboard.md`](M15_Patient_Dashboard.md) |
| **M16** | Evals & CI | 26-case golden eval end-to-end; CI jobs lint/test/migrations/frontend/compose; nightly + manual live Gemini eval | **COMPLETED** | **VERIFIED locally (actionlint clean; first Actions run pending)** | [`M16_Evals_and_CI.md`](M16_Evals_and_CI.md) |
| **M17** | Load Test & Polish | k6 measurements, restart persistence, backup/restore drill, nginx frontend container, security headers, a11y, demo seed | **COMPLETED** | **VERIFIED (Full Docker stack + 330 tests + Langfuse tracing)** | [`M17_Load_Testing_and_Polish.md`](M17_Load_Testing_and_Polish.md) |

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

### Phase 4 Verification (Executed 2026-11-11)
- **Scope:** M10–M12. M13 not started.
- **Environment:** Linux sandbox, Python 3.12, PostgreSQL 16.15 + pgvector 0.6.0, Redis 7.0.15, Node 22, LangGraph 1.2.20 (native services; Docker Hub unreachable, so container images were not rebuilt here).
- **Docker Compose:** `docker compose config` valid (no Compose changes in Phase 4).
- **Migrations:** 0007 → 0008 → 0009 applied to the existing Phase 3 database; `app_role` bootstrap re-run; full up/down round trip and model/migration sync verified by tests.
- **End-to-end (native API + `arq` worker as non-owner role, `LLM_PROVIDER=fake`):**
  - `/health` ok; `arq --check` healthy.
  - Chat "Is my HbA1c getting worse?" answered from the computed comparison with 2 citations; history 4 messages.
  - "I have chest pain right now" → `urgent: true`; injection question blocked.
  - Document deletion 204, repeat 404, residual rows 0, citing chat removed, file removed; audit holds counts only.
  - App role sees 0 checkpoints/medications without patient context; no PHI or secrets in logs.
- **Safety eval (in-sample, hand-written):** red-flag recall 22/22, precision 1.0; injection block 8/8, benign false blocks 0/8; diagnostic block 12/12, factual false blocks 0/10.
- **Test Suite Results:** 289 passed, 0 failed, 0 skipped.
- **Linting & Code Quality:** `ruff check .` clean; `ruff format --check .` 152 files compliant; frontend `npm run build` passes (frontend unchanged).

### Phase 5 Verification (Executed 2026-11-11)
- **Environment:** Linux sandbox, 1 vCPU / 4 GB, Python 3.12, PostgreSQL 16.15 + pgvector 0.6.0, Redis 7.0.15, Node 22, k6 0.54.0, nginx 1.24 (native services; Docker Hub unreachable, so images were not built here).
- **Backend:** `pytest`: **321 passed, 0 failed, 0 skipped** (M0–M12 regression included; Phase 5 added 32).
- **Frontend:** Vitest **13 passed, 0 failed**; `vite build` passes.
- **Quality:** `ruff check .` clean; `ruff format --check .` 177 files compliant; `actionlint` clean.
- **Migrations:** fresh database: upgrade → `alembic check` (no drift) → app role → downgrade base → upgrade, head `0011`. Test suite round trip passes.
- **Golden eval (fake provider):** answers 9/12, not-found 1.0, isolation 1.0, red flags 1.0, injection 1.0, 0 cross-patient / 0 ungrounded citations.
- **Load (k6, 1 vCPU):** reads p95 24.3 ms @208 req/s; ask p95 79.6 ms @53 req/s (fake LLM); login p95 449.6 ms; doctor view p95 17.6 ms @158 req/s; processing p95 656 ms; 0 errors in 13,102 requests.
- **Operations:** restart persistence verified; backup/restore drill verified; nginx production config verified (headers, proxy, IP-spoof resistance, 413 body limit).
- **Compose:** `docker compose config` valid (services: postgres, redis, migrate, api, worker, web).
- **Security scan:** no secret patterns or hardcoded credentials found.

### Phase 5 Blocker Resolution & Final Local Verification (Executed 2026-11-11)
- **Environment:** Windows 11 host with Docker Desktop 29.9.3 (WSL2 engine) + Python 3.12.8, Node.js 22.12.0.
- **Blockers Resolved:**
  1. Frontend / Rollup cross-platform build: Fixed `package.json` optionalDependencies and `package-lock.json` for win32-x64-msvc and linux-x64-musl (Alpine).
  2. Langfuse tracing: Integrated `langfuse==5.2.0` with deterministic PHI masking layer (`mask_phi`, `pseudonymize_id`), fail-safe error handling, and zero PHI egress.
- **Docker Stack:** All 5 containers (`postgres`, `redis`, `api`, `worker`, `web`) healthy and serving traffic; `migrate` exited 0 with no Alembic drift.
- **Backend Full Test Suite:** **330 passed, 0 failed, 0 skipped** (321 base + 8 tracing unit + 1 agent tracing integration).
- **Frontend Test Suite & Build:** Vitest **13 passed, 0 failed**; `vite build` completed in 4.99s.
- **Quality & Hygiene:** `ruff check .` clean (0 errors); `ruff format --check .` 191 files compliant; repository hygiene test passed (0 committed secrets).
- **Golden Evaluation:** 26 clinical cases; 100% isolation, 100% red flag accuracy, 100% injection block rate, 0 cross-patient citations, 0 ungrounded citations.
- **Doctor Sharing Security:** 19/19 security tests passed.
- **20-Step Synthetic Patient E2E Workflow:** All 20 steps passed against live Docker containers.
- **Final Verdict:** `READY — all previously identified blockers are fixed and regression verification passes`.
