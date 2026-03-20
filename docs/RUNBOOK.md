# Operations Runbook (Stage 2)

This runbook is for day-to-day operation of the current `rfq_manager_ms` V1 service.

## 1) Prerequisites

- Python 3.11+ (for local venv mode)
- Docker + Docker Compose (for integrated local stack)
- PostgreSQL connectivity
- Required env var: `DATABASE_URL`

## 2) Start / Stop

### Option A: Docker Compose (preferred)

Start:

```bash
docker compose up --build -d
```

Stop:

```bash
docker compose down
```

### Option B: Local venv

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn src.app:app --reload --port 8000
```

## 3) Health and Smoke Checks

Run after startup and after any operational change:

1. Health endpoint: `GET /health` returns `200` and `{"status":"ok"}`.
2. API docs page loads: `/docs`.
3. RFQ list endpoint responds: `GET /rfq-manager/v1/rfqs`.
4. Reminder stats endpoint responds: `GET /rfq-manager/v1/reminders/stats`.

## 4) Database and Seed Operations

Apply latest migrations:

```bash
alembic upgrade head
```

Seed scenarios:

```bash
python scripts/seed.py --scenario=minimal
python scripts/seed.py --scenario=demo --seed=42
python scripts/seed.py --scenario=blocked-rfqs
python scripts/seed.py --scenario=completed-lifecycle
```

Reset and reseed:

```bash
python scripts/seed.py --scenario=demo --reset --seed=42
```

## 5) Reminder Processing (Current V1 Behavior)

- Batch reminder processing is triggered on demand via endpoint:
  - `POST /rfq-manager/v1/reminders/process`
- Test email endpoint is log-only in V1:
  - `POST /rfq-manager/v1/reminders/test`
- No real outbound email provider is active in current implementation.

## 6) Common Incidents and Actions

### Incident: app fails at startup with configuration error

Symptoms:

- Runtime error references missing/invalid `DATABASE_URL`.

Actions:

1. Set `DATABASE_URL` to a valid SQLAlchemy URL.
2. Restart API process.
3. Re-run health checks.

### Incident: API starts but DB operations fail

Symptoms:

- 5xx errors on endpoints that read/write DB.

Actions:

1. Verify PostgreSQL container/service is running.
2. Confirm DB host/port/credentials in `DATABASE_URL`.
3. Run `alembic upgrade head` to ensure schema is current.
4. Re-run smoke checks.

### Incident: reminder processing returns zero processed

Possible causes in current logic:

- no reminders due
- reminders already hit `max_sends`
- same-day rate-limit gate via `last_sent_at`

Action:

1. Inspect reminder due dates/status/send counters.
2. Re-run process endpoint when reminders are eligible.

### Incident: file upload/read issues

Actions:

1. Verify `FILE_STORAGE_PATH` exists and is writable by API process.
2. In Compose mode, verify host `./uploads` bind mount and permissions.

## 7) CI Baseline

Current CI workflow on `main` executes:

- `ruff check src tests scripts`
- `pytest -q`

Use the same commands locally before promotion.
