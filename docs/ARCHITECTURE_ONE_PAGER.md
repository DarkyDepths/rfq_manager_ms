# Architecture One-Pager (Stage 2)

## Purpose

`rfq_manager_ms` is a FastAPI microservice for RFQ lifecycle operations: RFQ creation, workflow/stage progression, subtasks, reminder management, and file handling.

## Runtime Shape

- API framework: FastAPI
- ORM/data access: SQLAlchemy 2.x
- Migrations: Alembic
- Primary datastore: PostgreSQL
- Validation/serialization: Pydantic v2

## Request Flow

1. Request enters FastAPI route (`src/routes/*`).
2. Route resolves controller through dependency providers in `src/app_context.py`.
3. Controller applies business logic and transaction boundaries.
4. Datasource executes ORM queries against SQLAlchemy session.
5. Translator returns response models.

## Layer Responsibilities

- `routes/`: HTTP contract and request parsing.
- `controllers/`: orchestration, validation-by-use-case, commit behavior.
- `datasources/`: direct database queries and persistence helpers.
- `models/`: SQLAlchemy schema models.
- `translators/`: Pydantic request/response schemas and model mapping.
- `services/`: batch/background-friendly domain logic (e.g., reminders processing).
- `connectors/`: external integration seams (IAM/event bus placeholders in V1).
- `config/`: environment-driven settings with fail-fast DB validation.

## API Surface (Current)

- Total endpoints: 31
- Base path: `/rfq-manager/v1`
- Resource groups:
  - RFQ (7)
  - Workflow (3)
  - RFQ Stage (6)
  - Subtask (4)
  - Reminder (7)
  - File (3)
  - Health (1)

## Data Model Snapshot

- Active operational tables include RFQ, workflow/stage template, RFQ stage, subtask, note, file, reminder, and reminder rule.
- Two schema-present but dormant tables in V1: `rfq_stage_field_value`, `rfq_history`.

## Cross-Cutting Behavior

- CORS middleware configured from `CORS_ORIGINS`.
- V1 auth bypass middleware can inject demo user context when enabled.
- Global error handling normalizes `AppError` and request validation failures.
- Health endpoint at `/health` supports liveness checks.

## Deployment Baseline

- Local integrated deployment via `docker-compose.yml`.
- Container build via `Dockerfile`.
- CI baseline in `.github/workflows/ci.yml` runs `python scripts/verify.py` (ruff + pytest + startup/import sanity).
