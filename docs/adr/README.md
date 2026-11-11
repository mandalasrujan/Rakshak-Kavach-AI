# Architecture Decision Records

One ADR per significant decision (about 10 lines: context, decision, rejected alternative, consequences). Copy `0000-template.md` for new ADRs and never edit an accepted ADR's decision; supersede it with a new one.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-pgvector-in-postgres.md) | pgvector in the main PostgreSQL | Accepted |
| [0002](0002-arq-for-background-jobs.md) | ARQ on Redis for background jobs | Accepted |
| [0003](0003-single-agent.md) | One agent with three tools | Accepted |
| [0004](0004-jwt-cookie-and-csrf.md) | JWT in an httpOnly cookie with CSRF header check | Accepted |
| [0005](0005-streaming-vs-output-guard.md) | Return the full guarded answer (no token streaming in v1) | Accepted |
| [0006](0006-deterministic-tool-routing.md) | Deterministic tool routing for the agent | Accepted |
| [0007](0007-rls-langgraph-checkpointer.md) | LangGraph checkpointer on our own RLS tables | Accepted |
| [0008](0008-doctor-share-access.md) | Doctor share access via hashed token + PIN and an RLS owner lookup | Accepted |
| [0009](0009-versioned-snapshots.md) | Versioned, approve-once summary snapshots built from SQL | Accepted |
| [0010](0010-same-origin-frontend.md) | Serve the frontend and API on one origin through nginx | Accepted |
