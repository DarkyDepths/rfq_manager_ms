# Smoke Demo (Stage 5 Release Proof)

This is the single authoritative smoke/demo path for leadership and reviewer validation.

## 1) Prerequisites

- Docker Desktop / Docker Engine is running.
- Docker Compose v2 is available.
- Ports `18000` (manager API), `18081` (manager mock event bus), and `15432` (manager scenario PostgreSQL) are free.

## 2) Authoritative Startup

```bash
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full
```

Expected outcome:

- The curated scenario stack completes successfully.
- The manager API is reachable on `http://localhost:18000/health`.
- The manager-side scenario data is already seeded.

If it fails:

```bash
python ../scripts/rfqmgmt_scenario_stack.py verify --seed-set full
```

Mock event bus quick check:

```bash
curl -sS http://localhost:18081/
```

Expected response:

```json
{"status":"ok","service":"mock_event_bus"}
```

Minimal local proof sequence (PowerShell):

```powershell
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full
(Invoke-WebRequest http://localhost:18000/health).Content
(Invoke-WebRequest http://localhost:18081/).Content
```

## 3) UI Startup

```bash
cd ../rfq_ui_ms
npm run dev
```

Expected outcome:

- The UI starts locally and can target the scenario-stack APIs.

If it fails:

- Check the UI dev server output.
- Re-run `python ../scripts/rfqmgmt_scenario_stack.py verify --seed-set full`.

## 3.1) Required Local Compose Wiring (Validated)

- `AUTH_BYPASS_ENABLED: "true"`
- `AUTH_BYPASS_TEAM: Estimation`
- `AUTH_BYPASS_USER_NAME: Mohamed Guidara`
- `EVENT_BUS_URL: http://event_bus_mock:8081/events`

These values are set through the scenario stack and manager-side `docker-compose.scenario.yml`.

## 3.2) Postman Validation Order (Validated)

Run Postman in this order:

1. Folder 0
2. Folder 1

Then verify event delivery:

```bash
docker compose -p rfq-manager-scenario -f docker-compose.scenario.yml logs --tail 100 event_bus_mock
```

## 4) Authoritative Smoke/Demo Sequence

Use one of the two equivalent paths below.

### PowerShell

```powershell
$env:BASE_URL = "http://localhost:18000"

# Step 1: /health
$health = Invoke-RestMethod "$env:BASE_URL/health"
$health

# Step 2: /docs reachable (expect 200)
(Invoke-WebRequest "$env:BASE_URL/docs").StatusCode

# Step 3: list RFQs
$rfqList = Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs"
$rfqList.data.Count

# Step 4: inspect one RFQ
$rfqId = $rfqList.data[0].id
$rfq = Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs/$rfqId"
$rfq.id

# Step 5: verify stage/workflow-related behavior (stages listed for RFQ)
$stages = Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs/$rfqId/stages"
$stages.data.Count

# Step 6: verify one secondary capability (reminder stats)
Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/reminders/stats"

# Step 7: confirm service remains stable
Invoke-RestMethod "$env:BASE_URL/health"
```

### Bash / zsh

```bash
BASE_URL="http://localhost:18000"

# Step 1: /health
curl -fsS "$BASE_URL/health"

# Step 2: /docs reachable (expect 200)
curl -sS -o /dev/null -w "%{http_code}\n" "$BASE_URL/docs"

# Step 3: list RFQs (copy one `id` value from output)
curl -fsS "$BASE_URL/rfq-manager/v1/rfqs"

# Step 4: inspect one RFQ
RFQ_ID="<paste-rfq-id-from-step-3>"
curl -fsS "$BASE_URL/rfq-manager/v1/rfqs/$RFQ_ID"

# Step 5: verify stage/workflow-related behavior (stages listed for RFQ)
curl -fsS "$BASE_URL/rfq-manager/v1/rfqs/$RFQ_ID/stages"

# Step 6: verify one secondary capability (reminder stats)
curl -fsS "$BASE_URL/rfq-manager/v1/reminders/stats"

# Step 7: confirm service remains stable
curl -fsS "$BASE_URL/health"
```

Expected outcomes:

1. `/health` returns `{ "status": "ok" }`.
2. `/docs` returns status `200`.
3. RFQ list count is `>= 1`.
4. RFQ detail returns the same `id` selected from list.
5. Stage list count is `>= 1` for the selected RFQ.
6. Reminder stats returns a valid JSON payload.
7. Final `/health` remains `{ "status": "ok" }`.

If a step fails:

1. Re-run verification: `python ../scripts/rfqmgmt_scenario_stack.py verify --seed-set full`
2. Re-check the UI dev server
3. Retry only the failed smoke step

## 5) Stop / Reset After Demo

Stop services:

```bash
python ../scripts/rfqmgmt_scenario_stack.py down --remove-volumes
```

Full reset (containers + DB volume):

```bash
python ../scripts/rfqmgmt_scenario_stack.py down --remove-volumes
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full
```

## 6) Local Event Delivery Verification (H4 + mock bus)

After seed and smoke list/get steps:

PowerShell:

```powershell
$env:BASE_URL = "http://localhost:18000"
$rfqList = Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs"
$rfqId = $rfqList.data[0].id
$stages = Invoke-RestMethod "$env:BASE_URL/rfq-manager/v1/rfqs/$rfqId/stages"
$stageId = $stages.data[0].id
Invoke-RestMethod -Method Post "$env:BASE_URL/rfq-manager/v1/rfqs/$rfqId/stages/$stageId/advance"
docker compose -p rfq-manager-scenario -f docker-compose.scenario.yml logs --tail 100 event_bus_mock
```

Bash / zsh:

```bash
BASE_URL="http://localhost:18000"
RFQ_ID=$(curl -fsS "$BASE_URL/rfq-manager/v1/rfqs" | python -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")
STAGE_ID=$(curl -fsS "$BASE_URL/rfq-manager/v1/rfqs/$RFQ_ID/stages" | python -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")
curl -fsS -X POST "$BASE_URL/rfq-manager/v1/rfqs/$RFQ_ID/stages/$STAGE_ID/advance"
docker compose -p rfq-manager-scenario -f docker-compose.scenario.yml logs --tail 100 event_bus_mock
```

Expected outcome:

- Stage advance endpoint returns success (`200`).
- `event_bus_mock` logs show `EVENT RECEIVED` and the JSON envelope posted by `rfq_manager_ms`.

Validated local V1 proof now covers:

- API healthy (`/health`)
- DB healthy (compose health)
- Metrics exposed (`/metrics`)
- Request IDs present in responses (`X-Request-ID`)
- Postman Folder 0 and Folder 1 demo path
- File upload flow (within Postman/demo path)
- Event delivery to local mock bus (`event_bus_mock` logs)
