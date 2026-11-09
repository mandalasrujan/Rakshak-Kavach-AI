# ADR 0003: One agent with three tools

- **Status:** Accepted
- **Date:** 2026-11-10

**Context.** Questions are about one patient's records: narrative text, lab values and medications. Multiple agents would mostly be different prompts over the same data.

**Decision.** One LangGraph Medical History Agent with three tools: `search_records`, `get_labs`, `get_medications`. Graph order is fixed: consent, red-flag rules, agent, output guard.

**Rejected alternative.** Several specialised agents behind a router: more LLM calls, routing errors, and harder evaluation.

**Consequences.** Fewer LLM calls, reliable tool choice, simpler evals. Specialised agents are reconsidered only if evals show the single agent underperforms.
