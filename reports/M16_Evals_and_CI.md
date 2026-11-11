# Milestone Report: M16 — Evaluations and CI

## Objective
Reproducible evaluation sets and CI that fails when retrieval, safety, isolation or security regress.

- **Spec deliverable:** 25 to 30 golden cases, CI with a mocked LLM, and a manual or nightly live-LLM eval job.
- **Spec "done when":** CI fails if leakage, red-flag, guard or recall tests regress.

## Evaluation suites (all synthetic data)
| Suite | Size | Runs in | Measures |
|---|---|---|---|
| `evals/golden_cases.yaml` → `tests/evals/test_golden_eval.py` | **26 cases**, 2 patients, 14 PDFs | CI (fake provider); live job (Gemini) | answer correctness with expected citations, not-found, isolation, red flags, injection, cross-patient and ungrounded citations, end to end through the API, agent, PostgreSQL/RLS and pgvector |
| `evals/retrieval_questions.yaml` → `scripts/eval_retrieval.py` | 20 questions | CI (fake, artifact); live job (Gemini) | retrieval hit@6; RAG vs long-context answer accuracy |
| `evals/tool_selection.yaml` | 10 questions | CI (unit) | deterministic tool routing |
| `evals/safety_cases.yaml` | 22 + 20 red-flag, 8 + 8 injection, 12 + 10 output | CI (unit) | red-flag recall/precision, injection block/false block, guard block/false block |
| Synthetic generator labels | 30 lab rows | CI (unit) | lab extraction precision/recall |

## Measured results (offline `fake` provider, 2026-11-11)
**Golden eval:**
| Metric | Result |
|---|---|
| Answer accuracy | **0.75** (9/12) |
| Not-found accuracy | 1.0 |
| Isolation accuracy | 1.0 |
| Red-flag accuracy | 1.0 |
| Injection block rate | 1.0 |
| Cross-patient citations | 0 |
| Ungrounded citations | 0 |

The three failing answer cases (G05 allergy, G07 blood pressure, G10 CT) involve long narrative chunks that the hash embedder scores below the 0.2 similarity threshold. That is a limitation of the offline provider, not a Gemini result.

**Other suites:**
- Retrieval hit@6 = 0.90; RAG and long-context answer accuracy 0.85 each (fake provider).
- Tool selection 10/10.
- Safety: red-flag recall 22/22 and precision 1.0 (in-sample); injection 8/8 blocked with 0/8 false blocks; output guard 12/12 blocked with 0/10 false blocks.
- Extraction precision and recall 1.0 on 30 rows.

**These are pipeline and guard measurements with a deterministic stand-in. No Gemini call was made in this environment, and no Gemini quality is claimed.**

## Thresholds (CI gates)
- **Hard invariants (any provider):**
  - red-flag accuracy 1.0;
  - injection block rate 1.0;
  - cross-patient citations 0;
  - ungrounded citations 0.
- **Fake-provider regression gates:** answer ≥ 0.75, not-found ≥ 1.0, isolation ≥ 1.0. These are set to the first measured run, so they detect regressions; they are not quality targets.
- **Unit suites:**
  - Safety metrics are asserted exactly.
  - Tool selection must be 10/10.
  - Extraction must be 1.0.
- **Leakage and RLS:** M6, M10 and M14 tests are part of `pytest`.

## CI (`.github/workflows/ci.yml`)
| Job | Steps |
|---|---|
| `lint` | `ruff check .`, `ruff format --check .` |
| `test` | disposable `pgvector/pgvector:pg16` and `redis:7.4-alpine` services → full `pytest` (backend, security, leakage, safety, golden eval) → offline retrieval eval → upload `eval-results/` |
| `migrations` | fresh database: `alembic upgrade head` → `alembic check` (no model drift) → `python -m app.db.app_role` → `downgrade base` → `upgrade head` |
| `frontend` | `npm ci`, `npm test`, `npm run build` |
| `compose` | generated throwaway `.env` (`LLM_PROVIDER=fake`) → `docker compose up --build --wait` → smoke tests on API and web (`/health`, 401 on a protected route, the SPA served, `/api` through nginx) |

`live-eval.yml` runs manually and nightly. It needs the Gemini secret and variables, and skips with a warning if they are missing. It runs the golden eval with `EVAL_LLM_PROVIDER=gemini` plus the retrieval eval, uploads the results, and fails only on the hard invariants.

## Verification here
- Golden eval passed (1 test, 26 cases); the full backend suite is 321 passed.
- `actionlint` 1.7.12: no findings on all workflows.
- The migration job's steps were run locally on a fresh database: upgrade, `alembic check` ("No new upgrade operations detected"), app role, downgrade base, upgrade (head 0011). All exit 0.
- **GitHub Actions itself was not run from here** (no repository access); the workflows are syntax- and lint-checked only.

## Files
- **New:** `evals/golden_cases.yaml`, `tests/evals/test_golden_eval.py`, `.github/workflows/live-eval.yml`.
- **Modified:** `.github/workflows/ci.yml`, `pyproject.toml` (`eval` marker), `.gitignore` (`eval-results/`, `load-results/`).

## Known limitations
- No live Gemini numbers yet.
- The golden set is small (26) and written by the developer.
- Safety metrics are in-sample.
- Answer accuracy with the fake provider reflects the hash embedder.

## Status
**`M16: COMPLETED AND VERIFIED`** (locally; first GitHub Actions run pending)
