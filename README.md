# Rakshak Kavach AI

Rakshak Kavach AI is a patient health records assistant. Patients upload digital medical PDFs (lab reports, imaging reports, prescriptions, doctor notes) and chat with a single Medical History Agent that answers only from their own records, with page-level citations. Lab values are extracted, normalized and compared in plain code, urgent symptoms are caught by deterministic rules, and patients can share a read-only, patient-approved summary with a doctor through a QR code and PIN. It does not diagnose, predict or prescribe.

**Status:** Phase 2 complete: M0–M2 (foundation and authentication) and M3–M5 (consent and audit, document upload and queue, table-aware extraction). Next milestone: M6 (embeddings and isolation). The live deployment needs a host to be configured; see [docs/deployment.md](docs/deployment.md).

**Specification:** [`PROJECT_SPEC.md`](PROJECT_SPEC.md) is the source of truth. Working rules are in [`AGENTS.md`](AGENTS.md).

## What is implemented

- Docker Compose stack: PostgreSQL 16 + pgvector, Redis, one-shot Alembic migrations, FastAPI API, ARQ worker, all with healthchecks.
- Layered FastAPI app (router → service → repository → model), `/api/v1` prefix, one error schema, request IDs, PHI-free JSON logs.
- `GET /health` (200 when PostgreSQL and Redis are reachable, otherwise 503).
- Patient auth: `POST /api/v1/auth/register`, `POST /api/v1/auth/login` (argon2id, JWT in an `httpOnly`, `Secure`, `SameSite=Lax` cookie), `POST /api/v1/auth/logout` (token revoked in Redis), protected `GET /api/v1/patient/me`, CSRF and cross-site checks, login and registration rate limits.
- Consent: `GET/POST/DELETE /api/v1/patient/consent` (versioned notice disclosing Gemini processing); uploads require active consent; every consent and document event is written to an append-only `audit_log`.
- Documents: `POST /api/v1/patient/documents` (PDF only by magic bytes, size limit, per-patient dedup, 202), `GET /api/v1/patient/documents[/{id}]`; the ARQ worker validates (encryption, page limit), extracts one chunk per lab-table row plus page-numbered narrative chunks, and marks the document `ready` or `failed` with a reason.
- OpenAPI docs at `/api/v1/docs`.
- Synthetic PDF generator, 5 ADRs, one-page threat model, CI (lint, tests, Compose smoke test) and a provider-agnostic deploy workflow.

## Run with Docker Compose

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD (URL-safe) in all three places it appears,
# and JWT_SECRET_KEY to: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build --wait
curl http://127.0.0.1:8000/health
```

Try the auth flow (state-changing requests need the `X-CSRF-Protection: 1` header):

```bash
H='-H Content-Type:application/json -H X-CSRF-Protection:1'
curl $H -d '{"email":"demo@example.com","password":"demo-password-123"}' http://127.0.0.1:8000/api/v1/auth/register
curl $H -c jar.txt -d '{"email":"demo@example.com","password":"demo-password-123"}' http://127.0.0.1:8000/api/v1/auth/login
curl -b jar.txt http://127.0.0.1:8000/api/v1/patient/me
curl -b jar.txt http://127.0.0.1:8000/api/v1/patient/consent             # read notice_version
curl -b jar.txt $H -d '{"notice_version":"<version>"}' http://127.0.0.1:8000/api/v1/patient/consent
curl -b jar.txt -H X-CSRF-Protection:1 -F file=@report.pdf http://127.0.0.1:8000/api/v1/patient/documents
curl -b jar.txt http://127.0.0.1:8000/api/v1/patient/documents             # status: queued → ready
curl -b jar.txt -X POST -H X-CSRF-Protection:1 http://127.0.0.1:8000/api/v1/auth/logout
```

## Develop and test

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest
```

Integration tests need PostgreSQL 16 with pgvector and Redis. With Docker running, `pytest` starts them through Testcontainers. To use existing services instead, point the tests at a dedicated test database (tests truncate tables) and Redis DB 15:

```bash
docker compose up -d postgres redis
docker compose exec postgres createdb -U rakshak rakshak_test
export TEST_DATABASE_URL=postgresql+asyncpg://rakshak:<password>@127.0.0.1:5432/rakshak_test
export TEST_REDIS_URL=redis://127.0.0.1:6379/15
pytest
```

Other commands:

```bash
alembic -c backend/alembic.ini upgrade head                         # uses MIGRATION_DATABASE_URL
alembic -c backend/alembic.ini revision --autogenerate -m "message"
python scripts/generate_synthetic_pdfs.py --out data/synthetic      # 14 synthetic PDFs + manifest
```

## Layout

```
backend/    FastAPI app (app/), Alembic migrations, API Dockerfile
worker/     ARQ worker and Dockerfile
tests/      unit/ and integration/ tests
scripts/    synthetic PDF generator
docs/       ADRs, threat model, deployment notes
frontend/   React app (from M7)
```
