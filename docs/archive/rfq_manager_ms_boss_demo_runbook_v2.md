# RFQ Manager MS — Boss Demo Runbook v2

> **Service:** `rfq_manager_ms` · **Version:** V1 Baseline  
> **Audience:** BACAB Leadership Demo · PFE Defense Backup  
> **Runtime:** ~12 min full · ~5 min compressed  
> **Shell:** PowerShell (Windows) — adapt `Invoke-WebRequest` → `curl` for Linux/Mac  
> **Last updated:** March 2026

---

## Demo Objective

Prove that `rfq_manager_ms` is a solid V1 RFQ lifecycle backbone — ready for its first industrialization milestone: containerized delivery.

The demo proves eight things in sequence:

1. The stack starts cleanly from zero
2. The API is healthy and connected
3. The database is alive and accepting queries
4. Deterministic demo data loads reliably
5. The Postman business flow works end-to-end
6. Observability primitives are in place
7. Lifecycle events are really emitted and received locally
8. The service is reproducible — anyone can run this from a cold start

---

## Pre-Demo Checklist

Before you start, confirm these are true:

| # | Check | Command / Action |
|---|-------|-----------------|
| 1 | Docker Desktop is running | Whale icon in system tray is stable |
| 2 | No stale containers from previous runs | `docker compose down -v` |
| 3 | Port 8000 is free (API) | `netstat -ano \| findstr :8000` → empty |
| 4 | Port 5432 is free (Postgres) | `netstat -ano \| findstr :5432` → empty |
| 5 | Port 8081 is free (Event bus mock) | `netstat -ano \| findstr :8081` → empty |
| 6 | Postman collections are imported | Folder 0 + Folder 1 visible |
| 7 | Terminal is open in the repo root | `ls docker-compose.yml` succeeds |

> **If any port is occupied:** Kill the process or change the port mapping in `docker-compose.yml`. Do NOT demo on a dirty environment.

---

## Step 1 — Start the Local Stack

### Commands

```powershell
docker compose down -v          # clean slate — no leftover volumes
docker compose up -d --build    # build images + start all services
docker compose ps               # verify container states
```

### Speaking Script

> "I start from a completely clean state — no leftover containers, no stale data. One command builds and starts the entire V1 stack: the FastAPI application, PostgreSQL, and a local mock event bus. This is a reproducible environment — anyone on the team gets the same result from the same command."

### Expected Output

```
NAME              STATUS          PORTS
rfq_api           healthy         0.0.0.0:8000->8000/tcp
rfq_postgres      healthy         0.0.0.0:5432->5432/tcp
rfq_event_bus_mock running        0.0.0.0:8081->8081/tcp
```

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `rfq_api` shows `unhealthy` | DB connection refused — Postgres not ready yet | Wait 10s, check `docker compose logs api` |
| `rfq_postgres` exits immediately | Port 5432 already in use | `docker compose down -v`, kill local Postgres |
| Build fails on `pip install` | Network issue or bad `requirements.txt` | Check `docker compose logs api --tail 50` |

### Time: ~60–90 seconds (build) · ~10 seconds (startup)

---

## Step 2 — Prove Health of API and Event Bus

### Commands

```powershell
(Invoke-WebRequest http://localhost:8000/health).Content
(Invoke-WebRequest http://localhost:8081/).Content
```

### Speaking Script

> "Two health checks. The first proves the API process is alive and its internal wiring — database connection, route registration — is functional. The second proves the local event receiver is reachable, which I will use later to demonstrate real lifecycle event delivery."

### Expected Output

**API:**
```json
{"status": "ok"}
```

**Mock Event Bus:**
```json
{"status": "ok", "service": "mock_event_bus"}
```

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Connection refused on :8000 | Container not healthy yet | `docker compose ps` → wait for healthy |
| Health returns but DB error in logs | `DATABASE_URL` misconfigured | Check `.env` or compose environment block |
| :8081 refuses | Event bus container crashed | `docker compose logs event_bus_mock` |

### Time: ~5 seconds

---

## Step 3 — Load Deterministic Demo Data

### Command

```powershell
docker compose exec -e PYTHONPATH=/app api python scripts/seed.py --scenario=demo --reset --seed=42
```

### Speaking Script

> "I load a deterministic demo dataset with a fixed random seed. This means every run produces the same RFQs, the same workflows, the same stage progressions. This is not random test data — it is a stable, repeatable baseline that I can validate against known expected values. The `--reset` flag ensures we start from a clean database state."

### Expected Output

```
Seed scenario: demo
Reset: True
Random seed: 42
─────────────────────
RFQs created: X
  ├── INQUIRY: ...
  ├── ESTIMATION: ...
  ├── SUBMITTED: ...
  └── ...
Workflows: ...
Reminders: ...
─────────────────────
Demo seed complete.
```

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError` | PYTHONPATH not set | Ensure `-e PYTHONPATH=/app` is in the command |
| `FileNotFoundError: seed.py` | Wrong script path | Verify path is `scripts/seed.py` (not `src/scripts/`) |
| `IntegrityError` on insert | Seed ran without `--reset` on dirty DB | Add `--reset` flag |
| `OperationalError: connection refused` | DB container not ready | `docker compose ps` → wait for postgres healthy |

### Time: ~5–10 seconds

---

## Step 4 — Prove Business-Level Responsiveness

### Commands

```powershell
(Invoke-WebRequest http://localhost:8000/docs).StatusCode
(Invoke-WebRequest http://localhost:8000/rfq-manager/v1/rfqs).StatusCode
```

### Speaking Script

> "This goes beyond health. The first call proves the OpenAPI documentation is generated and served — meaning route registration worked correctly. The second call hits the actual business API surface and retrieves real RFQ data from the database. A 200 here means the full stack is wired: routes, controllers, datasources, database."

### Expected Output

```
200
200
```

### Optional Deep Check

```powershell
# Count RFQs to verify seed loaded
$r = Invoke-WebRequest http://localhost:8000/rfq-manager/v1/rfqs
($r.Content | ConvertFrom-Json).data.Count
```

This should return the number of RFQs created by the seed script.

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `/docs` returns 404 | FastAPI app misconfigured | Check `app.py` includes swagger |
| `/rfqs` returns 500 | Seed didn't run or DB schema mismatch | Re-run seed, check `docker compose logs api` |
| `/rfqs` returns 200 but empty list | Seed ran but `--reset` dropped data after insert | Re-run seed command |

### Time: ~5 seconds

---

## Step 5 — Run Postman Baseline

### What to Do

In Postman, execute in this order:

1. **Folder 0 — Bootstrap & Baseline:** Initializes runtime variables, validates platform connectivity
2. **Folder 1 — Continuous Boss Demo:** Runs the full RFQ lifecycle story

### Speaking Script

> "This is the core of the demo. Folder 0 is the bootstrap — it initializes runtime variables and confirms the platform is reachable from Postman. Folder 1 is the real story: it walks through the entire RFQ lifecycle that `rfq_manager_ms` owns."

> *(As Folder 1 runs, narrate each section:)*

> "We create a new RFQ — the system assigns a unique ID and auto-generates the workflow stages. We retrieve it. We advance through stages — the system enforces progression order. We create reminders tied to the RFQ. We upload and download files. And finally, we export the data as CSV. This is the lifecycle backbone."

### What to Highlight During Execution

| Postman Section | What It Proves |
|-----------------|---------------|
| RFQ creation → 201 | System generates UUID, creates linked stages automatically |
| RFQ retrieval → 200 | Data persists correctly, relationships resolve |
| Stage advancement → 200 | Business logic enforces valid transitions |
| Reminder CRUD | Cross-entity operations work within the same lifecycle |
| File upload/download | Azure Blob integration (or local stub) functions |
| CSV export → 200 | Reporting capability exists at the API level |

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Folder 0 fails on first request | Base URL variable wrong in Postman | Set `{{base_url}}` to `http://localhost:8000` |
| Stage advance returns 400 | Trying to skip a stage | Follow the sequence in the collection order |
| File upload returns 500 | Blob storage not configured / mock not running | Check environment config for storage backend |

### Time: ~3–5 minutes (depending on narration pace)

---

## Step 6 — Prove Observability

### Commands

```powershell
# Correlation ID on every request
$r = Invoke-WebRequest http://localhost:8000/health
$r.Headers["X-Request-ID"]

# Prometheus-style metrics endpoint
$m = Invoke-WebRequest http://localhost:8000/metrics
$m.StatusCode
```

### Speaking Script

> "Every single request that enters the service gets a unique correlation ID — the `X-Request-ID` header. This is a production fundamental: when something fails, you can trace the entire request path through logs using this ID. The `/metrics` endpoint exposes Prometheus-compatible metrics — request counts, latencies, error rates. This means the service is ready to plug into any standard monitoring stack."

### Expected Output

```
X-Request-ID: a3f1b2c4-5d6e-7f8a-9b0c-1d2e3f4a5b6c    (UUID format)
/metrics status: 200
```

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No `X-Request-ID` header | Middleware not registered | Check `app.py` middleware setup |
| `/metrics` returns 404 | Prometheus middleware not installed | Verify `prometheus-fastapi-instrumentator` in requirements |

### Time: ~10 seconds

---

## Step 7 — Prove Real Lifecycle Event Delivery

This is the finale and the most important proof.

### Action

In Postman, perform one event-producing action:

- **Option A:** Create a new RFQ (triggers `rfq.created`)
- **Option B:** Advance a stage (triggers `stage.advanced`)

Then immediately run:

```powershell
docker compose logs --tail 100 event_bus_mock
```

### Speaking Script

> "This is the final and most important proof. I just created an RFQ through the API — that is a business action. But watch the event bus logs."

> *(Show the logs)*

> "The service did not just process the request internally. It published a real lifecycle event — `rfq.created` — to the event bus. The mock receiver captured it with the full payload: the RFQ ID, the timestamp, the event type. This is the integration seam. In production, `rfq_communication_ms` would pick this up to send notifications. `rfq_intelligence_ms` would pick it up to trigger proactive analysis. The microservice is not a silo — it is a platform citizen that announces what happened so other services can react."

### Expected Output in Logs

```
=== EVENT RECEIVED ===
path: /events
method: POST
body:
{
  "event_type": "rfq.created",
  "rfq_id": "...",
  "timestamp": "...",
  ...
}
========================
```

Or for stage advancement:

```
=== EVENT RECEIVED ===
path: /events
body:
{
  "event_type": "stage.advanced",
  "rfq_id": "...",
  "stage": "...",
  ...
}
========================
```

### Failure Signatures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No `EVENT RECEIVED` in logs | Event publisher not wired to mock bus URL | Check `EVENT_BUS_URL` env var in compose |
| Event fires but payload is empty | Serialization issue in event connector | Check `connectors/event_bus.py` |
| Mock bus container not running | Crashed during startup | `docker compose restart event_bus_mock` |

### Time: ~30 seconds

---

## Step 8 — Closing Statement

### Speaking Script

> "So at this point, we have demonstrated a complete local V1 proof:
>
> Clean stack startup from zero — reproducible by anyone.  
> Healthy API with database connectivity confirmed.  
> Deterministic demo data loaded with a fixed seed.  
> Full RFQ lifecycle validated through 40+ Postman scenarios: creation, retrieval, stage progression, reminders, files, and export.  
> Observability primitives in place: correlation IDs on every request, Prometheus metrics exposed.  
> And real lifecycle event delivery — the service publishes domain events that other platform services can consume.
>
> This is why I consider `rfq_manager_ms` a solid V1 backbone for the RFQ lifecycle platform, and why it is ready for its first industrialization milestone: containerized delivery."

---

## Compressed Emergency Version (~5 min)

If time is short, run this exact sequence:

```powershell
# 1. Clean start
docker compose down -v
docker compose up -d --build
docker compose ps

# 2. Health
(Invoke-WebRequest http://localhost:8000/health).Content
(Invoke-WebRequest http://localhost:8081/).Content

# 3. Seed
docker compose exec -e PYTHONPATH=/app api python scripts/seed.py --scenario=demo --reset --seed=42

# 4. Business proof
(Invoke-WebRequest http://localhost:8000/rfq-manager/v1/rfqs).StatusCode
```

Then in Postman:

```
→ Run Folder 0 (Bootstrap)
→ Run Folder 1 (Boss Demo)
→ Trigger one RFQ create or stage advance
```

Back in terminal:

```powershell
# 5. Event proof
docker compose logs --tail 100 event_bus_mock
```

Narrate: *"Stack from zero. Health confirmed. Demo data loaded. Lifecycle flow validated. Events delivered. V1 backbone proven."*

---

## Recovery Playbook — If Something Breaks During Demo

| Situation | Recovery |
|-----------|----------|
| Container won't start | `docker compose down -v && docker compose up -d --build` |
| API returns 500 | `docker compose logs api --tail 30` → read the traceback |
| Seed fails | `docker compose restart api` → re-run seed |
| Postman request fails | Check `{{base_url}}` is `http://localhost:8000`, retry |
| Event bus shows no events | `docker compose restart event_bus_mock` → retry the action |
| Everything is broken | `docker compose down -v` → start from Step 1 |
| Port conflict | `docker compose down` → `netstat -ano \| findstr :<PORT>` → kill PID |

> **Golden rule:** If in doubt, `docker compose down -v && docker compose up -d --build` resets everything. You lose 90 seconds, not the demo.

---

## Appendix: What Each Container Does

| Container | Image | Role | Health Check |
|-----------|-------|------|-------------|
| `rfq_api` | Built from Dockerfile | FastAPI application — 31 endpoints, 7 resources | `GET /health` → `{"status":"ok"}` |
| `rfq_postgres` | `postgres:15` | Operational database — 11 tables | TCP :5432 accepting connections |
| `rfq_event_bus_mock` | Lightweight HTTP server | Captures lifecycle events locally for demo | `GET /` → `{"status":"ok"}` |

## Appendix: The 6 Lifecycle Events

| Event Type | Trigger | What It Signals |
|------------|---------|----------------|
| `rfq.created` | POST /rfqs | A new RFQ entered the system |
| `rfq.status_changed` | Status field mutation | Overall RFQ status transitioned |
| `stage.advanced` | Stage progression endpoint | Workflow moved forward |
| `stage.blocked` | Blocker added to stage | Workflow is paused — attention needed |
| `reminder.created` | POST /reminders | A deadline reminder was set |
| `file.uploaded` | File upload endpoint | A document was attached to an RFQ |

---

*This runbook is both a demo script and a repeatable validation procedure. If every step passes, the service is confirmed healthy from a cold start.*
