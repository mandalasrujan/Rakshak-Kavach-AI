# Milestone Report: M6 — Embeddings and Isolation

## 1. Milestone Title and Objective
- **Milestone:** M6 — Embeddings and Isolation
- **Status:** COMPLETED
- **Objective:** Embed every chunk through an `LLMProvider`, store vectors in pgvector, and make cross-patient access impossible at the database layer (non-owner app role + RLS + transaction-scoped patient context).

## 2. Why This Milestone is Necessary
Retrieval (M7) must search only one patient's records. An application-level filter alone fails open if one query forgets it; RLS on a non-owner role fails closed.

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:** `LLMProvider`, `VectorStore` (pgvector), scoped repositories, RLS policies, non-owner app role, embedding model stored per chunk (spec 4.2: `SET LOCAL app.patient_id` per transaction; owner bypass; migrations as owner; 4.3: exact search, no HNSW).
- **Acceptance Criteria:** "Leakage tests pass, including a query with the patient filter deliberately removed."

## 4. Architecture and Implementation
```
API request / worker job
  └─ set_patient_context(session, patient_id)      # session.info + immediate set_config(..., true)
       after_begin listener ─► SELECT set_config('app.patient_id', :id, true)  (= SET LOCAL)
  └─ PgVectorStore(session, patient_id).search()  # patient filter + RLS + embedding_model filter
PostgreSQL: policy patient_isolation USING/WITH CHECK
            (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
```
### 4.1 Key Design Choices
- **Provider boundary:** `app/llm/base.py` protocol; `GeminiProvider` (REST via httpx; key in `x-goog-api-key` header; `outputDimensionality=768`; vectors re-normalized); `FakeLLMProvider` (deterministic hashed bag-of-words, offline) refused when `APP_ENV=production`. Missing key/models → API starts, `/ask` returns 503; worker marks documents `embedding_unavailable`.
- **Embedding dimension 768**, fixed by `chunks.embedding vector(768)`; model name stored per chunk and used as a search filter.
- **Non-owner role:** migration 0006 creates NOLOGIN group `rakshak_app` with least-privilege grants (`audit_log`: SELECT/INSERT only; no TRUNCATE anywhere). `python -m app.db.app_role` creates/updates the LOGIN role (password quoted server-side with `format(%I, %L)`, never logged) and refuses a role that owns tables. FORCE RLS is deliberately not set: the owner (migrations, admin) bypasses, the app role cannot.
- **Context:** a SQLAlchemy `after_begin` listener re-applies the local setting to every transaction of a bound session (services commit mid-flow); a session cannot be rebound to another patient. Unbound sessions see zero patient-owned rows.
- `patients` has no RLS (login must look up by email before any patient context exists); app role has no DELETE on it.
- Reprocessing deletes and re-inserts chunks with embeddings in one transaction (no stale vectors).

## 5. Files and Folders Created or Modified
- New: `backend/app/llm/{__init__,base,gemini,fake,factory}.py`, `backend/app/db/patient_context.py`, `backend/app/db/app_role.py`, `backend/app/repositories/vector_store.py`, migrations `0005_chunk_embeddings.py`, `0006_app_role_and_rls.py`.
- Modified: `core/config.py` (shared `LLMSettings`), `db/session.py`, `models/chunk.py`, `repositories/chunk_repository.py`, `services/document_processing.py`, `api/deps.py` (`get_patient_session`), `main.py`, `worker/{config,main}.py`, `docker-compose.yml` (owner vs app URL, role bootstrap in `migrate`, LLM env), `.env.example`, `.github/workflows/ci.yml`, `requirements*.txt` (`pgvector`, `httpx` now runtime).
- Tests: `tests/unit/test_llm_providers.py`, `tests/integration/test_isolation.py`; `tests/conftest.py` (app connects as a test LOGIN role; assertions use an owner engine); existing integration tests switched their direct SQL from `app.state.engine` to the owner handle (required: the app role is now subject to RLS and cannot TRUNCATE).

## 6. Important Classes, Functions and APIs
- `LLMProvider.embed_documents / embed_query / generate_json / aclose`.
- `set_patient_context(session, patient_id)`; `PgVectorStore.search(query, embedding_model, limit, min_similarity) -> list[RetrievedChunk]` (document_id, page, kind, chunk_id, similarity).
- `ensure_app_login_role(owner_url, username, password)`.

## 7. Database Changes
- 0005: `CREATE EXTENSION vector`; `chunks.embedding vector(768)`, `chunks.embedding_model` (nullable: pre-M6 chunks need reprocessing).
- 0006: role `rakshak_app`, grants, RLS + `patient_isolation` policy on `consent_records`, `documents`, `chunks`, `audit_log`.

## 8. Security Considerations
Isolation is enforced three times: scoped repositories, explicit patient filter, and RLS on a role that owns nothing and has no BYPASSRLS. Writes for another patient fail `WITH CHECK`. Logs carry IDs/counts only.

## 9–10. Testing and Results
| Test | Scenario | Result |
|---|---|---|
| `test_llm_providers.py` (8) | fake determinism/normalization; Gemini request shape, batching (150→100+50), key only in header, HTTP/dimension/JSON errors, schema validation; placeholder settings; fake refused in production | **PASSED** |
| `test_app_role_owns_nothing_and_cannot_bypass_rls` | role not superuser/BYPASSRLS, owns 0 tables, RLS enabled, app connects as that role | **PASSED** |
| `test_missing_patient_context_sees_no_rows` | 0 rows in all 4 tables without context | **PASSED** |
| `test_patient_context_is_transaction_scoped` | setting gone after commit | **PASSED** |
| `test_rls_hides_other_patients_even_without_a_where_clause` | **acceptance**: unfiltered SELECT returns only own rows, also after commit | **PASSED** |
| `test_rls_rejects_writes_for_another_patient` | WITH CHECK violation | **PASSED** |
| `test_app_role_cannot_truncate_or_rewrite_audit` | permission denied | **PASSED** |
| `test_session_cannot_be_rebound_to_another_patient` | RuntimeError | **PASSED** |
| `test_vector_search_ranks_relevant_chunks_with_citation_metadata` | top hit + page/document metadata | **PASSED** |
| `test_vector_search_never_crosses_patients` | same file for two patients; misuse returns [] | **PASSED** |
| `test_embeddings_are_stored_and_replaced_on_reprocessing` | 768-dim + model; new ids, same count | **PASSED** |
| `test_missing_provider_fails_document_without_chunks` | `embedding_unavailable` | **PASSED** |
| `test_processing_and_search_logs_are_phi_free` | no names/values/emails in logs | **PASSED** |
| `test_infrastructure.py` | 0001→0007 up/down, models match | **PASSED** |

## 11. Problems Encountered and Fixes
1. Existing tests truncated/asserted through the app engine; with RLS and least privilege that is impossible by design. Tests now use an owner engine for setup/assertions while the app under test uses the non-owner role.
2. The signed-hash fake embedder lost similarity to sign collisions; switched to unsigned counts.

## 12. Verification Results
- Full suite 241 passed; Ruff/format clean.
- Native run: `alembic upgrade` 0004→0007 on the Phase 2 database, `app_role` bootstrap, API and worker connected as `rakshak_api`; app role sees 0 chunks/lab rows without context and gets `permission denied` on TRUNCATE; pgvector 0.6.0.
- Docker Compose: `docker compose config` valid; images not built here (Docker Hub unreachable).

## 13. Limitations and Pending Work
- Live Gemini calls were not exercised (no key or network access to the API here); the adapter is tested against mocked HTTP.
- Chunks created before M6 have no embeddings until their document is reprocessed (no backfill job).
- Existing local `.env` files need `APP_DB_USER`/`APP_DB_PASSWORD`, and `DATABASE_URL` must use the app role.

## 14. Final Milestone Status
**`M6: COMPLETED AND VERIFIED`**
