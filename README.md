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
- API contract sources:
  - [OpenAPI YAML (authoritative)](docs/rfq_manager_ms_openapi_current.yaml)
  - [HTML contract view (derived convenience view)](docs/rfq_manager_ms_api_contract_current.html)
  - [Swagger explorer shell (derived convenience view)](docs/rfq_manager_ms_swagger_current.html)

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

### Scenario Stack (authoritative for local platform testing)

```bash
# From rfq_manager_ms, start the curated scenario stack in the parent workspace
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full

# Start the UI separately in rfq_ui_ms
# npm run dev

# Stop and wipe the scenario stack when finished
python ../scripts/rfqmgmt_scenario_stack.py down --remove-volumes
```

This is the official local source of truth for end-to-end testing because it:

- boots the manager scenario compose file
- seeds curated RFQ scenarios via `scripts/seed_rfqmgmt_scenarios.py`
- produces the manifest consumed by the intelligence-side scenario stack

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
├── scripts/             # Bootstrap + dev/scenario seeding
├── alembic.ini          # Migration config
├── requirements.txt     # Python dependencies
├── requirements-dev.txt # Test/dev dependencies
├── Dockerfile           # API container image
├── docker-compose.scenario.yml # Manager-side compose for the curated scenario stack
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
