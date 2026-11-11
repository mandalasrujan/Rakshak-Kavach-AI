# Milestone Report: M10 — LangGraph Medical History Agent

## 1. Objective
Replace the M7 baseline orchestration with a LangGraph Medical History Agent that answers a patient's questions from their own records, with page citations, persisted conversation state, consent enforcement and patient isolation.

- **Spec deliverable:** LangGraph state and nodes, tools `search_records` / `get_labs` / `get_medications`, Postgres checkpointer, retrieved text treated as data, injection test cases.
- **Spec "done when":** correct tool chosen on 10 hand-written questions.

## 2. Implementation
```
START → consent → red_flags → input_guard → tools → answer → output_guard → finalize → END
        (no consent / urgent / blocked input / no evidence jump straight to finalize)
```
(The `red_flags`, `input_guard` and `output_guard` nodes belong to M11; this report covers the rest.)

- **`consent`:** `ConsentService.has_active_consent()` runs inside the graph, in addition to the route-level `require_consent`.
- **`tools` (deterministic, read-only, patient-scoped):**
  - `search_records`: pgvector search (M6).
  - `get_labs`: the deterministic M9 comparison, rendered as text marked "computed comparison". It cites the source chunk of both the latest and the previous result.
  - `get_medications`: the new `medications` table.
  - Routing is rule-based. Test names are matched against the M8 dictionary aliases; trend words add `get_labs`; medicine words add `get_medications`; `search_records` always runs. If there is no evidence, the LLM is not called.
- **`answer`:** the only LLM call. `LLMProvider.generate_json` returns `{found, answer, citations}`. The question, the last three turns of history and the evidence are HTML-escaped in tagged blocks marked as untrusted data. `ground()` keeps only citations to evidence that was provided and expands them to document/page/chunk sources.
- **`finalize`:** appends the user and assistant turns to `messages`, the only channel that persists between turns. It also records `message_citations` for persisted chats. Every node logs its name and latency, never content.
- **Checkpointer:**
  - `PatientCheckpointSaver` implements LangGraph's `BaseCheckpointSaver` on our own tables (`chat_checkpoints`, `chat_checkpoint_writes`).
  - Each operation opens a session bound to the patient, so checkpoints, which contain document text, sit under the same RLS as all other patient data and cascade-delete with their chat.
- **Medications:** prescription-table rows (M5 renders them as `Medicine: …; Dose: …` lines) are parsed deterministically into `medications`, with chunk provenance and the prescription date.
- **API:**
  - `POST /api/v1/patient/ask`: single turn, no stored chat; the response gains `urgent`.
  - `POST /api/v1/patient/chats` (consent required).
  - `GET /api/v1/patient/chats`.
  - `GET /api/v1/patient/chats/{id}/messages`.
  - `POST /api/v1/patient/chats/{id}/messages` (consent required; rate-limited with `/ask`).
  - `DELETE /api/v1/patient/chats/{id}`.

## 3. Important files
- **New:**
  - Agent: `backend/app/agent/{__init__,graph,tools,checkpointer,service}.py`.
  - Routes: `backend/app/api/v1/chats.py`.
  - Models: `backend/app/models/{chat,medication}.py`.
  - Repositories: `backend/app/repositories/{chat_repository,medication_repository}.py`.
  - Services: `backend/app/services/medication_extraction.py`.
  - Migration `0008_agent_chats_checkpoints_medications.py`; eval set `evals/tool_selection.yaml`.
- **Modified:**
  - `api/deps.py`: `get_agent_service` replaces `get_ask_service`.
  - `api/v1/ask.py`, `api/v1/router.py`, `schemas/ask.py`, `models/__init__.py`, `requirements.txt` (`langgraph==1.2.20`).
  - `services/document_processing.py`: stores medications.
  - `services/rag_service.py`: the M7 `AskService` was removed; the baseline prompt and grounding functions stay for `scripts/eval_retrieval.py`.
- **Tests:**
  - New: `tests/unit/test_agent_units.py`, `tests/integration/test_agent.py`.
  - `tests/integration/test_ask.py` (M7) now runs against the agent. Changes: the response includes `urgent`, and the log event is renamed `agent.answered`.

## 4. Design decisions
- **Deterministic tool routing instead of LLM function calling.**
  - Pros: tool choice is testable without a model, injected document text can never trigger or parameterise a tool, and there is one LLM call per turn. When nothing relevant is found, the LLM is still never called, which keeps the M7 guarantee.
  - Rejected alternative: Gemini function calling. It is nondeterministic, adds an extra call and opens an injection surface.
  - Trade-off: routing is keyword-based. Pronoun follow-ups ("is it getting worse?") still run `get_labs` for all tests and rely on the LLM plus chat history to resolve "it".
- **Own checkpointer instead of `langgraph-checkpoint-postgres`.**
  - Pros: no second driver (psycopg) or connection pool, Alembic-managed tables, and RLS plus cascade deletion apply to conversation state.
  - Trade-off: `PatientCheckpointSaver` stores whole serialized checkpoints rather than per-channel blobs.
- **LLM explains, Python computes:** lab trends reach the model as pre-computed text, and the prompt forbids recalculation (M11 enforces numbers).

## 5. Database changes (0008)
- New tables: `chats`, `message_citations` (chat ↔ document), `chat_checkpoints` and `chat_checkpoint_writes` (each with `patient_id`), and `medications` (spec columns plus `chunk_id`, `duration`, `raw_text`).
- Foreign keys cascade from patients, documents, chats and chunks.
- Every new table has least-privilege grants to `rakshak_app` and the `patient_isolation` RLS policy.

## 6. Tests and results
| Test | Scenario | Result |
|---|---|---|
| `test_tool_selection_eval_is_10_of_10` | **Spec acceptance:** 10 hand-written questions → correct tools and test codes (10/10) | **PASSED** |
| `test_short_ambiguous_aliases_are_not_matched` | "k", "na" not treated as tests; longest alias wins | **PASSED** |
| trend rendering, prompt escaping (incl. history), grounding, medications from prescription (2 rows, dedup) | deterministic units | **PASSED** (4) |
| `test_graph_has_the_expected_nodes` | graph structure | **PASSED** |
| `test_trend_question_uses_computed_comparison_with_both_sources` | "Is my HbA1c getting worse?" → computed comparison, cites both reports | **PASSED** |
| `test_medication_question_uses_structured_medications` | answer from `medications`, cited to prescription | **PASSED** |
| `test_chat_persists_conversation_in_rls_checkpoints` | history carried to turn 2; 4 messages; checkpoints owned by patient; invisible without context | **PASSED** |
| `test_chats_are_patient_scoped` | other patient: 404 for read/send/delete | **PASSED** |
| `test_deleting_a_chat_removes_its_conversation` | chats/checkpoints/writes/citations gone; audit `chat.deleted` | **PASSED** |
| `test_consent_is_enforced_inside_the_graph` | graph raises consent error even when the route check is bypassed | **PASSED** |
| `test_chat_routes_require_consent_and_csrf` | 403 / 201 | **PASSED** |
| M7 `test_ask.py` (14) | grounding, citations, not-found without LLM, cross-patient, injection-as-data, rate limit, 503, PHI-free logs, now via the agent | **PASSED** |

- **Full suite:** 289 passed, 0 failed, 0 skipped. Ruff and format are clean.
- **Native run:** a chat "Is my HbA1c getting worse?" was answered from the computed comparison with 2 citations; history held 4 messages; the app role sees 0 checkpoints without patient context.

## 7. Security considerations
- Patient context is set for the request session and for every checkpointer session.
- Chats are verified as the patient's own (RLS plus an explicit filter) before any read, send or delete.
- There are no tools that write, call out or act. Logs contain IDs, node names, counts and latency only.

## 8. Known limitations
- Live Gemini was not exercised; answers in tests and the native run come from the deterministic offline provider. The fake answerer matches exact tokens, so two tests use wording it can match (documented in the tests).
- Medications come only from prescription tables, not from free-text notes.
- Chats have no titles or retention period yet.
- The React chat still uses `/ask`; it is not yet wired to `/chats`.

## 9. Verification status
**`M10: COMPLETED AND VERIFIED`** (offline provider; live-model evaluation pending)
