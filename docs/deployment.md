# Deployment

The deploy pipeline is provider-agnostic: `.github/workflows/deploy.yml` runs after CI passes on `main`, pushes the API and worker images to GitHub Container Registry, calls your host's deploy hook, then polls the public `/health` URL.

## Host requirements

- PostgreSQL 16 with the `vector` extension available, and Redis 7.
- Two processes from the published images: the API (`backend/Dockerfile`, default command) and the worker (`worker/Dockerfile`).
- Run migrations before each API release, as the table owner: `alembic -c backend/alembic.ini upgrade head && python -m app.db.app_role` using the API image, with `MIGRATION_DATABASE_URL`, `APP_DB_USER` and `APP_DB_PASSWORD` set. The second command creates or updates the non-owner LOGIN role (member of `rakshak_app`) that the API and worker use; RLS applies to it. The owner needs CREATEROLE (or create the role manually with the same grants).
- A persistent volume for PostgreSQL data (and later for uploaded files, from M4).

## Configuration

Set these as environment variables on the host (never in the repository): `APP_ENV=production`, `DATABASE_URL` (the non-owner app role), `MIGRATION_DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY` (48+ random bytes), `FRONTEND_ORIGIN` (https), `ACCESS_TOKEN_EXPIRE_MINUTES`, `LLM_PROVIDER=gemini` with `GEMINI_API_KEY`, `GEMINI_CHAT_MODEL` and `GEMINI_EMBEDDING_MODEL` (the embedding model must support 768-dimension output). The API refuses to start in production with `COOKIE_SECURE=false`, an http frontend origin, or a short/placeholder JWT secret. Serve the frontend and API on the same site so `SameSite=Lax` cookies flow (ADR 0004). If the host terminates TLS in a proxy, set `FORWARDED_ALLOW_IPS` to the proxy address so client IPs used for rate limiting are correct.

## GitHub settings

| Name | Type | Purpose |
|---|---|---|
| `DEPLOY_HOOK_URL` | Secret | Host deploy hook URL (e.g. Render, Railway or Fly webhook) |
| `PUBLIC_BASE_URL` | Variable | Public base URL; the workflow requires `GET /health` to return 200 |

Without them the workflow publishes images and skips the deploy and smoke steps with a warning.

## Development-only settings

`COOKIE_SECURE=false` is for local plain-http testing only and is rejected when `APP_ENV=production`. Docker Compose binds Postgres, Redis and the API to `127.0.0.1` only.
