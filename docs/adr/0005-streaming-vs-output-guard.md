# ADR 0005: Return the full guarded answer (no token streaming in v1)

- **Status:** Accepted
- **Date:** 2026-11-10

**Context.** Every answer passes a deterministic output guard (diagnostic phrasing and numeric consistency). Token streaming would show text before the guard has seen the whole answer.

**Decision.** In v1 the chat endpoint returns the complete answer only after the output guard passes; the UI shows a waiting state.

**Rejected alternative.** Token streaming with post-hoc retraction: users would already have read blocked content.

**Consequences.** Higher perceived latency. Sentence-buffered streaming (guard each sentence before sending) can be added later behind the same guard.
