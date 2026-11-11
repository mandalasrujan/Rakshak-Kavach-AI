# Deployment

The deploy pipeline is provider-agnostic: `.github/workflows/deploy.yml` runs after CI passes on `main`, pushes the API and worker images to GitHub Container Registry, calls your host's deploy hook, then polls the public `/health` URL.

## Host requirements

- PostgreSQL 16 with the `vector` extension available, and Redis 7.
- Three containers: the API (`backend/Dockerfile`), the worker (`worker/Dockerfile`) and the web frontend (`frontend/Dockerfile`: nginx serving the built React app and proxying `/api` to the API on the same origin).
- TLS terminated in front of the web container. Add `Strict-Transport-Security` there; the app containers speak plain HTTP on an internal network.
- Run migrations before each API release, as the table owner: `alembic -c backend/alembic.ini upgrade head && python -m app.db.app_role` using the API image, with `MIGRATION_DATABASE_URL`, `APP_DB_USER` and `APP_DB_PASSWORD` set. The second command creates or updates the non-owner LOGIN role (member of `rakshak_app`) that the API and worker use; RLS applies to it. The owner needs CREATEROLE (or create the role manually with the same grants).
- A persistent volume for PostgreSQL data (and later for uploaded files, from M4).

## Configuration

Set these as environment variables on the host (never in the repository): `APP_ENV=production`, `DATABASE_URL` (the non-owner app role), `MIGRATION_DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY` (48+ random bytes), `FRONTEND_ORIGIN` (https), `ACCESS_TOKEN_EXPIRE_MINUTES`, `LLM_PROVIDER=gemini` with `GEMINI_API_KEY`, `GEMINI_CHAT_MODEL` and `GEMINI_EMBEDDING_MODEL` (the embedding model must support 768-dimension output). The API refuses to start in production with `COOKIE_SECURE=false`, an http frontend origin, or a short/placeholder JWT secret. Serve the frontend and API on the same site so `SameSite=Lax` cookies flow (ADR 0004). The API trusts `X-Forwarded-For` from `FORWARDED_ALLOW_IPS` (Compose uses `*` because the API port is bound to 127.0.0.1 and nginx overwrites the header). On a real host, set it to the proxy's address. Size `WEB_CONCURRENCY` to CPU cores; each API process opens up to 15 database connections (SQLAlchemy defaults).

## GitHub settings

| Name | Type | Purpose |
|---|---|---|
| `DEPLOY_HOOK_URL` | Secret | Host deploy hook URL (e.g. Render, Railway or Fly webhook) |
| `PUBLIC_BASE_URL` | Variable | Public base URL; the workflow requires `GET /health` to return 200 |

Without them the workflow publishes images and skips the deploy and smoke steps with a warning.

## Development-only settings

`COOKIE_SECURE=false` is for local plain-http testing only and is rejected when `APP_ENV=production`. Docker Compose binds Postgres, Redis and the API to `127.0.0.1` only.

## Live Gemini evaluation

`.github/workflows/live-eval.yml` runs nightly and on demand. It needs the `GEMINI_API_KEY` secret and the `GEMINI_CHAT_MODEL` / `GEMINI_EMBEDDING_MODEL` variables, and skips with a warning when they are missing. It uploads real Gemini scores as an artifact. Regular CI never calls Gemini.

## Demo

After `docker compose up --build --wait`:
```bash
docker compose cp scripts api:/app/scripts   # or run from a local venv
python scripts/seed_demo.py --base-url http://localhost:8080
```
This creates a synthetic demo patient with processed records and an approved summary, then prints the password once.
