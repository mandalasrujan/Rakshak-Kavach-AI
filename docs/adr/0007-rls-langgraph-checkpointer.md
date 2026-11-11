# ADR 0007: LangGraph checkpointer on our own RLS tables

- **Status:** Accepted
- **Date:** 2026-11-11

**Context.** Chat state persisted by LangGraph includes retrieved document text (PHI). It must be isolated per patient and deleted with the chat or with a cited document (M12).

**Decision.** Implement `BaseCheckpointSaver` (`PatientCheckpointSaver`) on Alembic-managed `chat_checkpoints` / `chat_checkpoint_writes` tables that carry `patient_id`, use the app's SQLAlchemy sessions bound with `set_patient_context`, and cascade from `chats`.

**Rejected alternative.** `langgraph-checkpoint-postgres`: adds psycopg and a second pool, manages its own tables and transactions, and its rows would sit outside RLS and our cascades.

**Consequences.** Conversation state gets RLS, least-privilege grants and FK cascade deletion. We maintain ~200 lines of saver code and store whole serialized checkpoints (no per-channel blob deduplication).
