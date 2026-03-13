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
# 1. Start Database (Docker)
docker run --name rfq_db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=rfq_manager_db -p 5555:5432 -d postgres:15

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env

# 5. Create tables & seed data
# Note: Ensure the port matches the docker command (5555)
$env:DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5555/rfq_manager_db'
alembic upgrade head
python scripts/seed.py --scenario=demo

# 6. Run the server
uvicorn src.app:app --reload --port 8000

# 7. Open API docs
# http://localhost:8000/docs
```

## Project Structure

```
rfq_manager_ms/
├── src/
│   ├── config/          # Settings (env vars)
│   ├── connectors/      # External service clients
│   ├── controllers/     # Business logic
│   ├── datasources/     # Database queries
│   ├── models/          # SQLAlchemy models (11 tables)
│   ├── routes/          # API endpoints
│   ├── translators/     # Pydantic schemas
│   ├── utils/           # Errors, pagination
│   ├── app.py           # FastAPI factory
│   ├── app_context.py   # Dependency injection
│   └── database.py      # Engine + session
├── migrations/          # Alembic migrations
├── tests/               # Unit + integration tests
├── seed.py              # DB init + sample data
├── alembic.ini          # Migration config
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
└── README.md
```

## Database Schema (11 tables)

| Table                   | Purpose                              |
|-------------------------|--------------------------------------|
| `rfq`                   | Core RFQ records                     |
| `workflow`              | Reusable workflow templates          |
| `stage_template`        | Stage definitions within workflows   |
| `rfq_stage`             | Live stage instances per RFQ         |
| `subtask`               | Tasks within stages (soft delete)    |
| `rfq_note`              | Append-only notes per stage          |
| `rfq_file`              | File attachments (soft delete)       |
| `rfq_stage_field_value` | Key-value captured data per stage    |
| `rfq_history`           | Audit trail                          |
| `reminder`              | Scheduled notifications              |
| `reminder_rule`         | Automation rules for reminders       |

## License

Proprietary — GHI internal use only.
