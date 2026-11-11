# ADR 0006: Deterministic tool routing for the agent

- **Status:** Accepted
- **Date:** 2026-11-11

**Context.** The Medical History Agent (M10) needs `search_records`, `get_labs` and `get_medications`. Uploaded documents may contain prompt-injection text, and the spec requires correct tool choice on hand-written questions.

**Decision.** Route tools with rules: test names (M8 dictionary aliases) or trend words add `get_labs`, medicine words add `get_medications`, and `search_records` always runs. All tools are read-only and patient-scoped. The LLM is called once, only to phrase an answer from the evidence.

**Rejected alternative.** LLM function calling: nondeterministic, an extra model call per turn, and injected text could steer tool selection or arguments.

**Consequences.** Tool choice is unit-testable (10/10 on `evals/tool_selection.yaml`); no LLM call when nothing is found. Keyword routing can miss unusual phrasing; `search_records` always runs as the fallback.
