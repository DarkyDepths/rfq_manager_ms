# Operations Runbook (Stage 2)

This runbook is for day-to-day operation of the current `rfq_manager_ms` V1 service.

## 1) Prerequisites

- Python 3.11+ (for local venv mode)
- Docker + Docker Compose (for integrated local stack)
- PostgreSQL connectivity
- Required env var: `DATABASE_URL` (for local venv / non-compose mode)

## 2) Start / Stop

### Option A: Scenario stack (preferred for end-to-end testing)

Start:

```bash
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full
```

Bootstrap note:

- The scenario stack starts `docker-compose.scenario.yml` for the manager side.
- It seeds curated RFQ scenarios through `scripts/seed_rfqmgmt_scenarios.py`.
- It also coordinates the paired intelligence-side scenario stack.

Inspect status:

```bash
python ../scripts/rfqmgmt_scenario_stack.py verify --seed-set full
```

Stop:

```bash
python ../scripts/rfqmgmt_scenario_stack.py down --remove-volumes
```

## 3) Health and Smoke Checks

Run after startup and after any operational change.

For the leadership/reviewer proof sequence (single authoritative demo path), use `docs/SMOKE_DEMO.md`.

Contract source note:

- `docs/rfq_manager_ms_openapi_current.yaml` is the authoritative API contract file.
- `docs/rfq_manager_ms_api_contract_current.html` and `docs/rfq_manager_ms_swagger_current.html` are derived convenience views and should not be edited or trusted ahead of the YAML.

PowerShell:

```powershell
$env:BASE_URL = "http://localhost:18000"

# 1) Health
Invoke-RestMethod "$env:BASE_URL/health"

# 1b) Metrics (Prometheus text format)
(Invoke-WebRequest "$env:BASE_URL/metrics").StatusCode

# 2) Docs page reachable (expect 200)
(Invoke-WebRequest "$env:BASE_URL/docs").StatusCode

# 3) Core RFQ smoke
Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs"

# 4) Reminder smoke
Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/reminders/stats"

# 5) Mock event bus health
(Invoke-WebRequest "http://localhost:18081/").Content

# 6) Event delivery log check
docker compose -p rfq-manager-scenario -f docker-compose.scenario.yml logs --tail 100 event_bus_mock
```

Bash / zsh:

```bash
BASE_URL="http://localhost:18000"

# 1) Health
curl -sS "$BASE_URL/health"

# 1b) Metrics (Prometheus text format)
curl -sS -o /dev/null -w "%{http_code}\n" "$BASE_URL/metrics"

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

Seed curated platform scenarios:

```bash
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full
```

## 5) Reminder Processing (Current V1 Behavior)

- Batch reminder processing is triggered on demand via endpoint:
  - `POST /rfq-manager/v1/reminders/process`
- Test email endpoint is log-only in V1:
  - `POST /rfq-manager/v1/reminders/test`
- No real outbound email provider is active in current implementation.

## 5.1) Request Correlation ID Baseline

- Every response includes `X-Request-ID`.
- Inbound `X-Request-ID` is preserved when valid.
- Inbound `X-Correlation-ID` is accepted as an alias.
- If missing/invalid, API generates a UUID request ID.
- Use `X-Request-ID` from responses to correlate logs during incident triage.

## 5.2) Event Publication Baseline (H4)

- Event seam is active through `EVENT_BUS_URL`.
- Current published lifecycle events:
  - `rfq.created`
  - `rfq.status_changed`
  - `rfq.deadline_changed`
  - `stage.advanced`
- Publication is best-effort and post-commit:
  - business DB commit is source of truth
  - publish is attempted after successful commit
  - publish failures are logged and do not roll back completed business writes
- Tune publication timeout with `EVENT_BUS_REQUEST_TIMEOUT_SECONDS`.

Validated scenario-stack wiring for stage-advance demo path:

- `AUTH_BYPASS_ENABLED: "true"`
- `AUTH_BYPASS_TEAM: Estimation`
- `AUTH_BYPASS_USER_NAME: Mohamed Guidara`
- `EVENT_BUS_URL: http://event_bus_mock:8081/events`

## 5.3) Dormant Model Decisions (H5)

- `rfq_history` remains intentionally dormant in V1 (no persisted audit-table writes in live controller flows).
- `rfq_stage_field_value` remains intentionally dormant in V1.
- V1 stage-form source of truth is `rfq_stage.captured_data`.
- For incident traceability in V1, use DB state + request-correlated logs + lifecycle events.

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
python ../scripts/rfqmgmt_scenario_stack.py verify --seed-set full
docker compose -p rfq-manager-scenario -f docker-compose.scenario.yml logs --tail 200 api
docker compose -p rfq-manager-scenario -f docker-compose.scenario.yml logs --tail 200 postgres
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

### Incident: event publication warnings in API logs

Symptoms:

- warning lines include `event_publish_failed` with `event_type` and request id.

Actions:

1. Verify `EVENT_BUS_URL` is configured and reachable from API runtime.
2. Validate downstream event service status and response codes.
3. Check timeout pressure and tune `EVENT_BUS_REQUEST_TIMEOUT_SECONDS` if needed.
4. Use request id from logs to correlate the business write and downstream publish attempt.

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
