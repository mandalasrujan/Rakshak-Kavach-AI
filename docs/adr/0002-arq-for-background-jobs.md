# ADR 0002: ARQ on Redis for background jobs

- **Status:** Accepted
- **Date:** 2026-11-10

**Context.** Extraction and embedding take 10 to 60 seconds and must not run inside API requests. The API is async FastAPI and Redis is already required for rate limiting.

**Decision.** Use ARQ workers on Redis. Jobs must be idempotent, retried on failure and record failure reasons. The worker healthcheck is `arq --check` on a short health-check interval.

**Rejected alternative.** Celery (heavier, sync-first, more configuration) and RQ (sync-only workers).

**Consequences.** Async code is shared between API and worker. ARQ has a smaller ecosystem than Celery; the queue is behind our own job-enqueue functions so it can be replaced.
