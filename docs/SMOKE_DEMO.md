# Smoke Demo (Stage 5 Release Proof)

This is the single authoritative smoke/demo path for leadership and reviewer validation.

## 1) Prerequisites

- Docker Desktop / Docker Engine is running.
- Docker Compose v2 is available.
- Port `8000` (API) and `5432` (PostgreSQL) are free.

## 2) Authoritative Startup

```bash
docker compose up --build -d
docker compose ps
```

Expected outcome:

- `postgres` is `healthy`.
- `api` is `running` (and becomes `healthy` shortly after startup).

If it fails:

```bash
docker compose logs --tail 200 postgres
docker compose logs --tail 200 api
```

## 3) Authoritative Seed Command

```bash
docker compose exec api python scripts/seed.py --scenario=demo --reset --seed=42
```

Expected outcome:

- Command completes successfully.
- Summary shows `rfqs_created` > 0.

If it fails:

- Check API logs: `docker compose logs --tail 200 api`
- Confirm API container is up: `docker compose ps`

## 4) Authoritative Smoke/Demo Sequence

Use one of the two equivalent paths below.

### PowerShell

```powershell
$env:BASE_URL = "http://localhost:8000"

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
BASE_URL="http://localhost:8000"

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

1. Re-check container status: `docker compose ps`
2. Re-check logs: `docker compose logs --tail 200 api`
3. Re-run seed command once: `docker compose exec api python scripts/seed.py --scenario=demo --reset --seed=42`
4. Retry only the failed smoke step.

## 5) Stop / Reset After Demo

Stop services:

```bash
docker compose down
```

Full reset (containers + DB volume):

```bash
docker compose down -v
docker compose up --build -d
docker compose exec api python scripts/seed.py --scenario=demo --reset --seed=42
```
