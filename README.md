# rfq_manager_ms

Core microservice for the RFQ Lifecycle Management platform. Manages RFQ creation, workflow-driven stage progression, task tracking, file management, and automated reminders.

## Architecture

```
routes/          →  API endpoints (FastAPI routers)
controllers/     →  Business logic & transaction management
datasources/     →  Database queries (SQLAlchemy ORM)
translators/     →  Pydantic schemas & model ↔ schema conversion
models/          →  SQLAlchemy table definitions (9 active, 2 dormant)
connectors/      →  External service clients (IAM auth resolution + HTTP event bus publication seam)
config/          →  Settings from environment variables
utils/           →  Shared helpers (errors, pagination)
```

## Operational Docs

- [Deployment approach](docs/DEPLOYMENT_APPROACH.md)
- [Operations runbook](docs/RUNBOOK.md)
- [Architecture one-pager](docs/ARCHITECTURE_ONE_PAGER.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Smoke demo (authoritative)](docs/SMOKE_DEMO.md)

## Quality Verification (Authoritative)

Run this before opening a PR:

```bash
pip install -r requirements-dev.txt
python scripts/verify.py
```

What `scripts/verify.py` executes (in order):

1. `ruff check src tests scripts`
2. `pytest -q`
3. startup/import sanity (`create_app()`)

CI runs the same verifier script.

## Tech Stack

- **Framework:** FastAPI
- **ORM:** SQLAlchemy 2.x
- **Database:** PostgreSQL 16
- **Migrations:** Alembic
- **Validation:** Pydantic v2
- **Python:** 3.11+

## Observability Baseline (H3)

- Request correlation IDs are now enforced at the app boundary.
	- Incoming `X-Request-ID` is preserved when valid.
	- Incoming `X-Correlation-ID` is accepted as an alias.
	- If missing/invalid, the service generates a UUID request ID.
	- Effective ID is returned in response header `X-Request-ID`.
- Minimal Prometheus-style metrics are exposed at `GET /metrics` (outside `/rfq-manager/v1`).
	- `rfq_manager_http_requests_total` (method, route template, status class)
	- `rfq_manager_http_request_duration_seconds` (method, route template)
- This baseline is intentionally minimal and does not include full tracing/export pipelines (no OTel vendor integration in this repo).

## Event Publication Baseline (H4)

- Event seam is active via `EVENT_BUS_URL` (HTTP JSON envelope publishing).
- Event publication is best-effort and post-commit (business DB commit remains source of truth).
- H4 event types:
	- `rfq.created`
	- `rfq.status_changed` (only when status actually changes)
	- `rfq.deadline_changed` (only when deadline actually changes)
	- `stage.advanced`
- Publish failures are logged and observable, but do not roll back successful business writes.

## Dormant Model Decisions (H5)

- `rfq_history` is intentionally dormant in V1.
	- V1 traceability comes from database state, request-correlated logs, and lifecycle events.
	- Dedicated persisted audit-table writes are deferred by design.
- `rfq_stage_field_value` is intentionally dormant in V1.
	- V1 source of truth for stage form data is `rfq_stage.captured_data`.
	- Normalized per-field rows are deferred to a future phase if query/reporting needs require them.
- Decision record: `docs/ADR_H5_DORMANT_MODELS.md`.

## API Endpoints (31 business endpoints + operational endpoints)

| Resource    | Endpoints | Description                                  |
|-------------|-----------|----------------------------------------------|
| RFQ         | 7         | CRUD + stats + analytics + export            |
| Workflow    | 3         | List, get, update templates                  |
| RFQ Stage   | 6         | List, get, update, notes, files, advance     |
| Subtask     | 4         | CRUD with soft delete + progress rollup      |
| Reminder    | 7         | CRUD + rules + stats + test email + process  |
| File        | 3         | List, download, soft delete                  |
| Health      | 1         | Liveness check (operational endpoint)        |
| Metrics     | 1         | Prometheus-style metrics (operational endpoint) |

Base path for business endpoints: `/rfq-manager/v1`.
Operational endpoints outside v1: `/health`, `/metrics`.

| # | Method | Path | Resource |
|---|--------|------|----------|
| 1 | POST | /rfqs | RFQ |
| 2 | GET | /rfqs | RFQ |
| 3 | GET | /rfqs/export | RFQ |
| 4 | GET | /rfqs/{rfq_id} | RFQ |
| 5 | PATCH | /rfqs/{rfq_id} | RFQ |
| 6 | GET | /rfqs/stats | RFQ |
| 7 | GET | /rfqs/analytics | RFQ |
| 8 | GET | /workflows | Workflow |
| 9 | GET | /workflows/{workflow_id} | Workflow |
| 10 | PATCH | /workflows/{workflow_id} | Workflow |
| 11 | GET | /rfqs/{rfq_id}/stages | RFQ Stage |
| 12 | GET | /rfqs/{rfq_id}/stages/{stage_id} | RFQ Stage |
| 13 | PATCH | /rfqs/{rfq_id}/stages/{stage_id} | RFQ Stage |
| 14 | POST | /rfqs/{rfq_id}/stages/{stage_id}/notes | RFQ Stage |
| 15 | POST | /rfqs/{rfq_id}/stages/{stage_id}/files | RFQ Stage |
| 16 | POST | /rfqs/{rfq_id}/stages/{stage_id}/advance | RFQ Stage |
| 17 | POST | /rfqs/{rfq_id}/stages/{stage_id}/subtasks | Subtask |
| 18 | GET | /rfqs/{rfq_id}/stages/{stage_id}/subtasks | Subtask |
| 19 | PATCH | /rfqs/{rfq_id}/stages/{stage_id}/subtasks/{subtask_id} | Subtask |
| 20 | DELETE | /rfqs/{rfq_id}/stages/{stage_id}/subtasks/{subtask_id} | Subtask |
| 21 | POST | /reminders | Reminder |
| 22 | GET | /reminders | Reminder |
| 23 | GET | /reminders/stats | Reminder |
| 24 | GET | /reminders/rules | Reminder |
| 25 | PATCH | /reminders/rules/{rule_id} | Reminder |
| 26 | POST | /reminders/test | Reminder |
| 27 | POST | /reminders/process | Reminder |
| 28 | GET | /rfqs/{rfq_id}/stages/{stage_id}/files | File |
| 29 | GET | /files/{file_id}/download | File |
| 30 | DELETE | /files/{file_id} | File |
| 31 | GET | /health | Health |

## Quick Start

### Docker Compose (recommended)

```bash
# Prerequisite: Docker Desktop / Docker Engine must be running

# Build and start API + PostgreSQL
docker compose up --build -d

# Confirm both services are up
docker compose ps

# Check API health and docs
# http://localhost:8000/health
# http://localhost:8000/docs

# Seed demo data inside the API container
docker compose exec -e PYTHONPATH=/app api python scripts/seed.py --scenario=demo --seed=42

# Run the leadership/reviewer smoke path
# docs/SMOKE_DEMO.md

# Inspect bootstrap/runtime logs
docker compose logs --tail 200 api

# Stop services
docker compose down
```

### Local venv

```bash
# 1. Start PostgreSQL in Docker
docker run --name rfq_db -e POSTGRES_USER=rfq_user -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=rfq_manager_db -p 5432:5432 -d postgres:16
# Linux/Mac: same command

# If the container already exists, start it instead
# docker start rfq_db
# Linux/Mac: same command

# 2. Create virtual environment
python -m venv .venv
# Linux/Mac: python3 -m venv .venv

# 3. Activate virtual environment
.venv\Scripts\Activate.ps1
# Linux/Mac: source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
# Linux/Mac: pip install -r requirements.txt

# Optional but required for local tests/lint
# (seed works with runtime deps; dev deps provide richer Faker-generated data)
pip install -r requirements-dev.txt
# Linux/Mac: pip install -r requirements-dev.txt

# 5. Create local environment file
Copy-Item .env.example .env
# Linux/Mac: cp .env.example .env

# 6. Make repo root importable for scripts
$env:PYTHONPATH="."
# Linux/Mac: export PYTHONPATH=.

# 7. Configure database connection
$env:DATABASE_URL="postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"
# Linux/Mac: export DATABASE_URL="postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"

# 8. Run migrations
alembic upgrade head
# Linux/Mac: alembic upgrade head

# 9. Seed demo data
python scripts/seed.py --scenario=demo
# Linux/Mac: python scripts/seed.py --scenario=demo

# 10. Start the API
uvicorn src.app:app --reload --port 8000
# Linux/Mac: uvicorn src.app:app --reload --port 8000

# 11. Open Swagger
# http://localhost:8000/docs
```

## Configuration

| Variable | Required | Default | What it controls | Local/dev notes |
|---|---|---|---|---|
| DATABASE_URL | Yes | None | SQLAlchemy/Alembic database connection URL. | App now fails fast at startup when missing/invalid. Example: `postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db`. |
| AUTH_BYPASS_ENABLED | No | `false` | Enables explicit local/dev auth bypass mode and demo user context. | Keep `false` for production. Set `true` only for local development/testing. |
| AUTH_BYPASS_USER_ID | No | `v1-demo-user` | Demo user id injected when bypass mode is enabled. | Local/dev only. |
| AUTH_BYPASS_USER_NAME | No | `System` | Demo display name injected when bypass mode is enabled. | Local/dev only. |
| AUTH_BYPASS_TEAM | No | `workspace` | Demo team injected when bypass mode is enabled. | Local/dev only. |
| IAM_REQUEST_TIMEOUT_SECONDS | No | `3.0` | Timeout for IAM auth resolution requests. | Tune based on IAM latency/SLA. |
| FILE_STORAGE_PATH | No | `./uploads` | Base directory used for uploaded stage files. | In Docker Compose it is bind-mounted to `/app/uploads`. |
| MAX_FILE_SIZE_MB | No | `50` | Maximum allowed uploaded file size in MB. | Enforced by stage file upload controller. |
| CORS_ORIGINS | No | `*` | Comma-separated CORS allowlist consumed by FastAPI CORS middleware. | Use explicit origins outside local development. |
| JWT_SECRET | No | `dev-secret-change-in-production` | Reserved seam for future JWT signing/validation workflows. | Not used as a standalone auth mechanism in this service. |
| APP_ENV | No | `development` | Environment label for runtime context. | Informational in current V1 runtime behavior. |
| APP_DEBUG | No | `false` | Enables SQLAlchemy SQL echo logging when true. | Useful for local debugging only. |
| APP_PORT | No | `8000` | Intended service port setting. | Current startup commands pass port explicitly (`8000`); value is informational for now. |
| IAM_SERVICE_URL | No | empty string | Base URL for IAM auth resolution (`/auth/resolve`). | Required when `AUTH_BYPASS_ENABLED=false`. |
| EVENT_BUS_URL | No | empty string | HTTP endpoint receiving published event envelopes. | H4 baseline is best-effort publish after successful commits. |
| EVENT_BUS_REQUEST_TIMEOUT_SECONDS | No | `3.0` | Timeout for outbound event publication HTTP calls. | Keep low and bounded to avoid request-path stalls. |

## Project Structure

```
rfq_manager_ms/
├── src/
│   ├── config/          # Settings (env vars)
│   ├── connectors/      # External service definitions (IAM + event bus)
│   ├── controllers/     # Business logic
│   ├── datasources/     # Database queries
│   ├── models/          # SQLAlchemy models (9 active, 2 dormant)
│   ├── routes/          # API endpoints
│   ├── services/        # Service layer for background/batch logic
│   ├── translators/     # Pydantic schemas
│   ├── utils/           # Errors, pagination
│   ├── app.py           # FastAPI factory
│   ├── app_context.py   # Dependency injection
│   └── database.py      # Engine + session
├── migrations/          # Alembic migrations
├── tests/               # Unit + integration tests
├── scripts/             # DB init + sample data (`seed.py`)
├── alembic.ini          # Migration config
├── requirements.txt     # Python dependencies
├── requirements-dev.txt # Test/dev dependencies
├── Dockerfile           # API container image
├── docker-compose.yml   # Local API + Postgres stack
├── .github/workflows/ci.yml  # Lint + tests on push/PR
├── .env.example         # Environment template
└── README.md
```

## Database Schema (11 tables total, 9 active)

| Table                   | Purpose                              |
|-------------------------|--------------------------------------|
| `rfq`                   | Core RFQ records                     |
| `workflow`              | Reusable workflow templates          |
| `stage_template`        | Stage definitions within workflows   |
| `rfq_stage`             | Live stage instances per RFQ         |
| `subtask`               | Tasks within stages (soft delete)    |
| `rfq_note`              | Append-only notes per stage          |
| `rfq_file`              | File attachments (soft delete)       |
| `rfq_stage_field_value` | Normalized stage field rows (Schema-present / intentionally dormant in V1; source of truth is `rfq_stage.captured_data`) |
| `rfq_history`           | Persisted audit trail table (Schema-present / intentionally dormant in V1) |
| `reminder`              | Scheduled notifications              |
| `reminder_rule`         | Automation rules for reminders       |

## License

Proprietary — GHI internal use only.
