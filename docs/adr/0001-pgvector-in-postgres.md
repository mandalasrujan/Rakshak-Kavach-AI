# ADR 0001: pgvector in the main PostgreSQL

- **Status:** Accepted
- **Date:** 2026-11-10

**Context.** Chunks need semantic search, strict per-patient isolation, and deletion that removes a document and its vectors together. Each patient has at most a few hundred chunks.

**Decision.** Store embeddings in a `chunks` table in the main PostgreSQL 16 using pgvector, behind the `VectorStore` interface. Use exact search filtered by `patient_id` (no HNSW in v1).

**Rejected alternative.** A separate Chroma server: one more service, no transactional delete with relational rows, and RLS would not cover vectors.

**Consequences.** One datastore, transactional deletes, RLS and SQL joins apply to vectors. If vectors outgrow Postgres, swap the `VectorStore` implementation (e.g. Qdrant).
