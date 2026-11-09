# Rakshak Kavach AI

Rakshak Kavach AI is a patient health records assistant. Patients upload digital medical PDFs (lab reports, imaging reports, prescriptions, doctor notes) and chat with a single Medical History Agent that answers only from their own records, with page-level citations. Lab values are extracted, normalized and compared in plain code, urgent symptoms are caught by deterministic rules, and patients can share a read-only, patient-approved summary with a doctor through a QR code and PIN. It does not diagnose, predict or prescribe.

**Status:** Phase 1 complete: M0 (repository and tooling), M1 (skeleton), M2 (authentication). Next milestone: M3 (consent and audit). The live deployment needs a host to be configured; see [docs/deployment.md](docs/deployment.md).

**Specification:** [`PROJECT_SPEC.md`](PROJECT_SPEC.md) is the source of truth. Working rules are in [`AGENTS.md`](AGENTS.md).

## What is implemented

- Docker Compose stack: PostgreSQL 16 + pgvector, Redis, one-shot Alembic migrations, FastAPI API, ARQ worker, all with healthchecks.
- Layered FastAPI app (router → service → repository → model), `/api/v1` prefix, one error schema, request IDs, PHI-free JSON logs.
- `GET /health` (200 when PostgreSQL and Redis are reachable, otherwise 503).
- Patient auth: `POST /api/v1/auth/register`, `POST /api/v1/auth/login` (argon2id, JWT in an `httpOnly`, `Secure`, `SameSite=Lax` cookie), `POST /api/v1/auth/logout` (token revoked in Redis), protected `GET /api/v1/patient/me`, CSRF and cross-site checks, login and registration rate limits.
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
