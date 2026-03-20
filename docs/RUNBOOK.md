# Operations Runbook (Stage 2)

This runbook is for day-to-day operation of the current `rfq_manager_ms` V1 service.

## 1) Prerequisites

- Python 3.11+ (for local venv mode)
- Docker + Docker Compose (for integrated local stack)
- PostgreSQL connectivity
- Required env var: `DATABASE_URL` (for local venv / non-compose mode)

## 2) Start / Stop

### Option A: Docker Compose (preferred)

Start:

```bash
docker compose up --build -d
```

Bootstrap note:

- The API container runs Alembic migrations before starting Uvicorn.
- If migrations fail, API container startup fails fast and logs the error.

Inspect status:

```bash
docker compose ps
```

Inspect logs:

```bash
docker compose logs --tail 200 api
docker compose logs --tail 200 postgres
docker compose logs -f api
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

Run after startup and after any operational change.

For the leadership/reviewer proof sequence (single authoritative demo path), use `docs/SMOKE_DEMO.md`.

PowerShell:

```powershell
$env:BASE_URL = "http://localhost:8000"

# 1) Health
Invoke-RestMethod "$env:BASE_URL/health"

# 2) Docs page reachable (expect 200)
(Invoke-WebRequest "$env:BASE_URL/docs").StatusCode

# 3) Core RFQ smoke
Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs"

# 4) Reminder smoke
Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/reminders/stats"
```

Bash / zsh:

```bash
BASE_URL="http://localhost:8000"

# 1) Health
curl -sS "$BASE_URL/health"

# 2) Docs page reachable (expect 200)
curl -sS -o /dev/null -w "%{http_code}\n" "$BASE_URL/docs"

# 3) Core RFQ smoke
curl -sS "$BASE_URL/rfq-manager/v1/rfqs"

# 4) Reminder smoke
curl -sS "$BASE_URL/rfq-manager/v1/reminders/stats"
```

## 4) Database and Seed Operations

Apply latest migrations:

```bash
alembic upgrade head
```

Seed (Docker Compose authoritative path):

```bash
docker compose exec api python scripts/seed.py --scenario=demo --seed=42
```

Reset and reseed (Compose):

```bash
docker compose exec api python scripts/seed.py --scenario=demo --reset --seed=42
```

Seed scenarios (local venv / non-compose):

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

Useful log commands:

```bash
docker compose ps
docker compose logs --tail 200 api
docker compose logs --tail 200 postgres
```

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

Current CI workflow on `main` executes one authoritative command:

```bash
python scripts/verify.py
```

Verifier checks included:

- `ruff check src tests scripts`
- `pytest -q`
- startup/import sanity (`create_app()`)

Use the same verifier command locally before promotion.
