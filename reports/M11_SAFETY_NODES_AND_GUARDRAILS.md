# Milestone Report: M11 — Safety Nodes and Guardrails

## 1. Objective
Deterministic safety inside the agent graph: versioned red-flag rules with negation and context, input validation and prompt-injection blocking, and an output guard that blocks diagnosis, treatment advice, predictions, fabricated citations and numbers that are not in the evidence. Urgent guidance must not be overridable.

- **Spec deliverable:** red-flag rules in a config file, output guard, wiring into the graph, streaming-versus-guard design (ADR 0005), per-node latency.
- **Spec "done when":** negated phrasing is not flagged, and red-flag precision/recall and the guard false-block rate are recorded.

## 2. Implementation
- **Rules:** `backend/app/data/safety_rules.yaml`, version `2026-11-11`. It holds red-flag phrases, negators, clause breakers, history markers, two fixed messages, injection patterns and no-diagnosis output patterns.
- **Red flags (`red_flags` node):** `detect_red_flag()` runs on the patient's own message only, never on document text.
  - Rules: chest pain, breathing difficulty, stroke signs, loss of consciousness, seizure, bleeding, anaphylaxis (category `urgent`) and self-harm (category `crisis`).
  - Negation is detected within 5 tokens before the phrase, and does not cross clause breakers (`but`, `,` and so on): "no fever but chest pain" is still flagged.
  - History markers such as "history of" or "years ago" suppress a match; "an hour ago" does not.
  - Crisis rules deliberately ignore negation.
- **Precedence:** a match ends the turn with a fixed message (call 112/108; crisis: Tele-MANAS 14416) and `urgent: true`, before any retrieval or LLM call. `output_guard` re-asserts the urgent outcome as defence in depth, so the LLM cannot override it.
- **`input_guard`:** strips control characters and normalises whitespace. It then blocks the question with a fixed message, without calling the LLM, if it matches an injection rule. Rules: instruction override, prompt or developer-mode requests, role changes, and prompt-tag injection.
- **`output_guard`:** after citation grounding (M10), `check_output()` rejects an answer if:
  - it matches a no-diagnosis, no-treatment or no-prediction pattern, or
  - it contains any number not present in the evidence it was given (or in the question; numbers are normalised, so 7.60 equals 7.6).
  - A rejected answer is replaced by a fixed safe message with no citations. The guard can only replace answers with that message, never insert content.
- **Logging:** rule IDs only (`safety.red_flag`, `safety.input_blocked`, `safety.output_blocked`); never the matched text. Node latency comes from the M10 wrapper.
- **Streaming:** none; the full answer is guarded before it is returned (ADR 0005).

## 3. Important files
- **New:** `backend/app/data/safety_rules.yaml`, `backend/app/services/safety.py`, `evals/safety_cases.yaml`, `tests/unit/test_safety.py`, `tests/integration/test_agent_safety.py`.
- **Modified:** `backend/app/agent/graph.py` (three nodes and routing), `tests/integration/test_agent.py` (node set).

## 4. Design decisions
- **Rules in versioned YAML, not prompts:** urgency never depends on LLM obedience, and changes are reviewable.
- **Fail closed, never fix:** guards replace unsafe output with fixed text. They never rewrite or soften an answer.
- **The numeric check is strict:** any number missing from the evidence blocks the answer, so a model that adds an unstated reference value is rejected rather than trusted.
- **Wording follows spec rules:** the rules are "based on commonly documented warning signs" and are not clinically validated.

## 5. Database changes
None.

## 6. Tests and results
Measured on the hand-written synthetic eval set `evals/safety_cases.yaml`:

| Metric | First run | Final |
|---|---|---|
| Red-flag recall (22 urgent/crisis phrasings) | 0.82 (18/22) | **1.00 (22/22)** |
| Red-flag precision (with 20 benign/negated/historical phrasings) | 1.00 | **1.00** (0 false positives) |
| Injection block rate (8) / benign false blocks (8) | 1.00 / 0 | **1.00 / 0** |
| Diagnostic-output block rate (12) / factual false-block rate (10) | 1.00 / 0 | **1.00 / 0** |

The first run exposed two real gaps:
- `ago` counted as history even for "an hour ago".
- "X is Y" phrasings were missing ("face is drooping", "stools are black", "tongue is swelling").

Both were fixed in the rules. **The final numbers are measured on the same set the rules were tuned against (in-sample), so they are not an estimate of real-world performance.**

| Test | Scenario | Result |
|---|---|---|
| `test_safety_eval_metrics` | the metrics above | **PASSED** |
| negation/clauses/history (8) | incl. "no fever but chest pain", "ten minutes ago", curly apostrophe | **PASSED** |
| messages, versioning, input cleaning, numeric consistency (4 cases) | units | **PASSED** |
| `test_urgent_symptoms_return_fixed_guidance_before_any_retrieval_or_llm` | reassuring LLM never called; no tools/answer nodes ran; log has rule id only | **PASSED** |
| `test_crisis_message_and_persisted_in_chat` | crisis line in reply and stored history | **PASSED** |
| `test_negated_symptom_gets_a_normal_answer` | negation → normal answer | **PASSED** |
| `test_injection_in_the_question_is_blocked_without_llm` (3) | override, prompt request, tag injection | **PASSED** |
| `test_unsafe_llm_answers_are_replaced` (4) | diagnosis, treatment, invented number, prediction | **PASSED** |
| `test_supported_factual_answer_passes_the_guard` | grounded numbers pass, 2 citations | **PASSED** |

- **Full suite:** 289 passed. Ruff and format are clean.
- **Native run:** the chest-pain message returned `urgent: true`; the injection was blocked; logs contain neither the question text nor credentials.

## 7. Security considerations
- Document text cannot trigger red flags or tools.
- The question cannot rewrite prompt structure, because it is escaped and injection-checked.
- Answer content is bounded by citation grounding plus the output guard.
- Safety logs carry no PHI.

## 8. Known limitations
- Keyword rules can miss unusual phrasing, misspellings and non-English input (Hindi/Telugu intake is future work).
- The guard can miss diagnostic language outside its patterns. The numeric check can block correct answers that add numbers not printed in the evidence. Both are documented trade-offs.
- Red flags need clinician review before real use.

## 9. Verification status
**`M11: COMPLETED AND VERIFIED`**
