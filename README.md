# rfq_manager_ms

Core microservice for the RFQ Lifecycle Management platform. Manages RFQ creation, workflow-driven stage progression, task tracking, file management, and automated reminders.

## Architecture

```
routes/          →  API endpoints (FastAPI routers)
controllers/     →  Business logic & transaction management
datasources/     →  Database queries (SQLAlchemy ORM)
translators/     →  Pydantic schemas & model ↔ schema conversion
models/          →  SQLAlchemy table definitions
connectors/      →  External service clients (IAM, event bus)
config/          →  Settings from environment variables
utils/           →  Shared helpers (errors, pagination)
```

## Tech Stack

- **Framework:** FastAPI
- **ORM:** SQLAlchemy 2.x
- **Database:** PostgreSQL 16
- **Migrations:** Alembic
- **Validation:** Pydantic v2
- **Python:** 3.11+

## API Endpoints (31 total)

| Resource    | Endpoints | Description                                  |
|-------------|-----------|----------------------------------------------|
| RFQ         | 7         | CRUD + stats + analytics + export            |
| Workflow    | 3         | List, get, update templates                  |
| RFQ Stage   | 6         | List, get, update, notes, files, advance     |
| Subtask     | 4         | CRUD with soft delete + progress rollup      |
| Reminder    | 7         | CRUD + rules + stats + test email + process  |
| File        | 3         | List, download, soft delete                  |
| Health      | 1         | Liveness check                               |

## Quick Start

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

## Project Structure

```
rfq_manager_ms/
├── src/
│   ├── config/          # Settings (env vars)
│   ├── connectors/      # External service definitions (stubs/dormant in V1)
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
├── scripts/             # DB init + sample data (seed.py)
├── alembic.ini          # Migration config
├── requirements.txt     # Python dependencies
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
| `rfq_stage_field_value` | Key-value captured data (Schema-only / Dormant in V1)|
| `rfq_history`           | Audit trail (Schema-only / Dormant in V1) |
| `reminder`              | Scheduled notifications              |
| `reminder_rule`         | Automation rules for reminders       |

## License

Proprietary — GHI internal use only.
