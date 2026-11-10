# Milestone Report: M1 — Backend Skeleton

## 1. Milestone Title and Objective
- **Milestone:** M1 — Skeleton + Live Deploy
- **Status:** COMPLETED
- **Objective:** Establish the clean, layered backend architecture (`Router -> Service -> Repository`), typed configuration with runtime validation, database migration pipeline (Alembic), standard error envelope, request correlation ID tracking, PHI-redacted JSON logging, public `/health` endpoint, and CI/CD deployment configuration.

---

## 2. Why This Milestone is Necessary
Direct coupling between web frameworks (FastAPI), business rules, and database queries leads to unmaintainable systems that are difficult to test without network calls and prone to security bypasses. In a healthcare assistant application:
1. **Separation of Concerns:** Business logic (such as safety checks, consent checks, and token generation) must exist independent of HTTP transports so it can be invoked by background workers or tested with fast unit tests.
2. **Deterministic Error Handling:** Clients (e.g. React dashboard) need predictable, machine-readable error responses rather than arbitrary HTML stack traces or non-standard JSON payloads.
3. **Auditability & Traceability:** Every request must carry a correlation ID (`X-Request-ID`) across logs without leaking Protected Health Information (PHI) such as patient names, emails, or credentials into system logs.
4. **Early Deployment Discipline:** Deploying from Week 1 guarantees that container packaging and database migrations are tested on every merge.

---

## 3. Requirements from `PROJECT_SPEC.md`
According to `PROJECT_SPEC.md` (Milestone M1):
- **Core Deliverables:**
  - Layered application design: `router -> service -> repository`.
  - Type-safe application settings (`pydantic-settings`) with validation rules.
  - Alembic configuration supporting async migrations.
  - API router mounted under `/api/v1`.
  - Standardized error schema across all application exceptions.
  - Request-ID correlation middleware with structured JSON logging.
  - Public `/health` endpoint returning database and Redis statuses.
  - Continuous Integration (CI) and deployment workflows.
- **Acceptance Criteria:**
  - Public `/health` returns `200 OK` with component statuses.
  - An integration test demonstrates the required flow across all three layers (`router -> service -> repository`).

---

## 4. Architecture and Implementation

### 4.1 Layered Architecture Pattern
Rakshak Kavach AI enforces a strict unidirectional dependency rule:

```
┌────────────────────────────────────────────────────────┐
│                   HTTP / Web Layer                     │
│  FastAPI Routers (/api/v1/*, /health)                  │
│  - Parses HTTP requests and cookies                    │
│  - Validates schemas (Pydantic DTOs)                   │
│  - Calls Services (never Repositories directly)        │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                    Service Layer                       │
│  AuthService, HealthService, RateLimiter               │
│  - Implements deterministic business logic             │
│  - Enforces safety rules and state transitions         │
│  - Calls Repositories for data persistence             │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                  Repository Layer                      │
│  PatientRepository, Scoped Repositories                │
│  - Executes SQLAlchemy queries inside async sessions   │
│  - Encapsulates ORM models and database queries        │
│  - Never handles HTTP concepts or sends cookies        │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   Database Engine                      │
│  PostgreSQL 16 (asyncpg driver)                        │
└────────────────────────────────────────────────────────┘
```

### 4.2 Request Correlation & Logging Pipeline
Every inbound HTTP request flows through the Request Context middleware:
1. **Correlation ID:** Checks incoming headers for `X-Request-ID`. If missing, generates a fresh `uuid4().hex`.
2. **Context Binding:** Binds `request_id` into Python's `contextvars` so all structured log messages across the call stack automatically include the ID.
3. **PHI Redaction Processor:** A custom `structlog` processor (`redact_sensitive`) automatically redacts sensitive keys (`password`, `email`, `jwt`, `token`, `cookie`, `body`) before logs are serialized to JSON.
4. **Header Propagation:** Emits `X-Request-ID` and security headers (`X-Content-Type-Options: nosniff`) in the HTTP response.

### 4.3 Standard Error Envelope
All API errors follow the schema defined in `backend/app/core/errors.py`:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found",
    "details": null
  }
}
```

---

## 5. Files and Folders Created or Modified
- `backend/app/main.py`: FastAPI application factory, lifespan management, middleware registration, and exception handlers.
- `backend/app/core/config.py`: Settings model with production security validations.
- `backend/app/core/errors.py`: Standard error classes (`AppError`, `NotFoundError`, `ConflictError`, etc.) and exception handlers.
- `backend/app/core/logging.py`: Structured JSON logger configuration and key-based PHI redaction filter.
- `backend/app/core/request_context.py`: Request-ID correlation middleware and context variable management.
- `backend/app/db/session.py`: Async SQLAlchemy engine and sessionmaker (`create_async_engine`).
- `backend/app/db/base.py`: SQLAlchemy declarative base (`Base`).
- `backend/app/models/patient.py`: Patient SQLAlchemy ORM entity.
- `backend/app/repositories/patient_repository.py`: Data-access repository for patient records.
- `backend/app/services/health_service.py`: Service probing PostgreSQL and Redis liveness.
- `backend/app/schemas/health.py`: Schema definitions for health check endpoints.
- `backend/app/api/health.py`: Router for `/health`.
- `backend/app/api/v1/router.py`: Top-level `/api/v1` router aggregator.
- `backend/alembic.ini` & `backend/alembic/env.py`: Async Alembic migration harness.
- `backend/alembic/versions/0001_create_patients.py`: Initial schema migration.
- `.github/workflows/ci.yml`: Automated CI pipeline (lint, test, build).
- `.github/workflows/deploy.yml`: CD pipeline deploy hook.
- `docs/deployment.md`: Production deployment guide.
- `tests/integration/test_layer_chain.py`: End-to-end layer flow test.
- `tests/integration/test_health_and_errors.py`: Tests for health endpoints and error formatting.
- `tests/unit/test_config.py`: Unit tests for environment settings and validation guards.
- `tests/unit/test_logging.py`: Unit tests for log formatting and redaction.

---

## 6. Important Classes, Functions and APIs

### 6.1 Configuration (`backend/app/core/config.py`)
- `Settings`: Loads environment variables with validators:
  - `_async_postgres_url`: Verifies that `DATABASE_URL` starts with `postgresql+asyncpg://`.
  - `_strong_secret`: Requires `JWT_SECRET_KEY` length $\ge 32$ characters and rejects the placeholder `change-me`.
  - `_production_guards`: Forbids `COOKIE_SECURE=false` or non-HTTPS origins when `APP_ENV=production`.

### 6.2 Application Factory (`backend/app/main.py`)
- `create_app(settings)`: Instantiates the FastAPI application, initializes database connection pools and Redis clients during the lifespan context, registers exception handlers, and configures CORS.

### 6.3 Layer Flow Components
- `HealthService.check(session, redis)`: Runs `SELECT 1` on PostgreSQL and `PING` on Redis, returning structured component health.
- `PatientRepository.create(email, password_hash)`: Persists a new patient row and flushes the session.
- `PatientRepository.get_by_email(email)`: Fetches a single patient record by unique email.

---

## 7. Database Changes
Alembic migration `0001_create_patients.py`:
- Creates the `patients` table:
  - `id` (UUID, Primary Key, default `gen_random_uuid()`)
  - `email` (VARCHAR(255), Unique, Not Null, Indexed)
  - `password_hash` (VARCHAR(255), Not Null)
  - `created_at` (TIMESTAMPTZ, Not Null, default `clock_timestamp()`)

---

## 8. Security Considerations
1. **Credential Safety at Boot:** The application crashes immediately on startup if `JWT_SECRET_KEY` is too short or contains the placeholder string.
2. **Production Cookie & Origin Enforcement:** `COOKIE_SECURE=false` is rejected at startup in production environments.
3. **No Database Parameter Leakage:** SQL queries execute via parameter binding; parameters are never reflected in error messages or logs.
4. **Structured Redaction:** `redact_sensitive` strips email and authentication credentials even if inadvertently passed to logger calls.

---

## 9. Testing Methodology
- **Unit Testing:**
  - Verification of settings validation logic under development, test, and production configurations.
  - Verification of log formatting, request ID attachment, and sensitive key redaction.
- **Integration Testing:**
  - Spun up test containers for PostgreSQL and Redis to verify database sessions and transactions.
  - End-to-end layer flow test: Sends a request through an authenticated endpoint to create a row in the database through router, service, and repository layers, asserting each layer's role.
  - Error envelope verification: Tests that missing entities return standard `404` error envelopes and validation failures return standard `422` envelopes.

---

## 10. Test Cases and Actual Results

| Test File | Test Case | Purpose | Result |
|---|---|---|---|
| `tests/unit/test_config.py` | `test_jwt_secret_must_be_at_least_32_chars` | Enforce secret key length requirement | **PASSED** |
| `tests/unit/test_config.py` | `test_jwt_secret_cannot_be_placeholder` | Reject default `change-me` placeholder | **PASSED** |
| `tests/unit/test_config.py` | `test_production_requires_secure_cookie` | Enforce HTTPS cookies in production | **PASSED** |
| `tests/unit/test_config.py` | `test_production_requires_https_frontend` | Enforce HTTPS frontend origin in production | **PASSED** |
| `tests/unit/test_config.py` | `test_database_url_must_use_asyncpg` | Enforce asyncpg driver in database URL | **PASSED** |
| `tests/unit/test_logging.py` | `test_sensitive_keys_are_redacted` | Ensure passwords and tokens are masked | **PASSED** |
| `tests/unit/test_logging.py` | `test_request_id_in_log_event` | Ensure correlation IDs are bound to logs | **PASSED** |
| `tests/integration/test_health_and_errors.py` | `test_health_returns_ok_when_services_up` | Verify `/health` returns 200 with DB + Redis ok | **PASSED** |
| `tests/integration/test_health_and_errors.py` | `test_standard_error_envelope_on_404` | Verify structured error envelope on missing routes | **PASSED** |
| `tests/integration/test_health_and_errors.py` | `test_standard_error_envelope_on_validation_failure` | Verify structured error envelope on 422 | **PASSED** |
| `tests/integration/test_health_and_errors.py` | `test_request_id_header_propagated` | Verify `X-Request-ID` is echoed in response | **PASSED** |
| `tests/integration/test_layer_chain.py` | `test_router_service_repository_chain` | Demonstrate data flow across all 3 layers | **PASSED** |

---

## 11. Problems Encountered and Fixes
- **Asynchronous Session Lifecycles in Fast-Paced Tests:**
  - *Context:* During layer-chain testing, multiple tests sharing an engine could hit session state collisions if tables weren't cleared.
  - *Resolution:* Added an async fixture `_reset_state(app)` in `tests/conftest.py` that truncates the `patients` table with `CASCADE` and flushes the Redis test database before each test execution.

---

## 12. Verification Results
- Live curl against the running API container:
  ```bash
  curl http://127.0.0.1:8000/health
  # HTTP/1.1 200 OK
  # {"status":"ok","checks":{"database":"ok","redis":"ok"}}
  ```
- All M1 unit and integration tests passed cleanly.

---

## 13. Limitations and Pending Work
- Row-Level Security (RLS) is not yet active on the `patients` table (scheduled for M6 when multi-tenant chunk embeddings and isolation repositories are introduced).
- Public `/health` currently checks connection liveliness; deep readiness checks for background queue latency will be added in subsequent milestones.

---

## 14. Final Milestone Status
**`M1: COMPLETED AND VERIFIED`**
- Layering is clean, configurations are validated, the migration pipeline functions as expected, and test coverage is comprehensive.

