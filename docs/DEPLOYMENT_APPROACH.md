# Deployment Approach (Stage 2)

This document defines the current, implementation-true deployment approach for `rfq_manager_ms` V1.

## 1) Scope

- Covers how to run and promote the current API safely using the existing repository assets.
- Reflects current runtime behavior in `Dockerfile`, `docker-compose.yml`, `src/config/settings.py`, and `.github/workflows/ci.yml`.
- Does not introduce new platform architecture (Kubernetes, managed secrets, blue/green tooling, etc.).

## 2) Deployment Modes

### A. Local integrated stack (recommended for dev/QA)

Use Docker Compose to run API + PostgreSQL:

```bash
docker compose up --build -d
```

What this does:

- Starts `postgres:16` with health checks.
- Builds API image from local `Dockerfile`.
- Runs `alembic upgrade head` before starting Uvicorn.
- Exposes API on `:8000` and DB on `:5432`.

Stop stack:

```bash
docker compose down
```

### B. Local Python runtime (venv)

Use when developing/debugging without containerized API process:

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn src.app:app --reload --port 8000
```

`DATABASE_URL` must be set and valid before startup.

## 3) Configuration Contract

- `DATABASE_URL` is mandatory and fail-fast validated at import/startup.
- If missing, empty, or invalid, app startup raises a clear configuration `RuntimeError`.
- Other environment variables have defaults and are documented in `README.md`.

## 4) Build and Promotion Baseline

Current build artifact:

- Single API container image from `Dockerfile`.

Current CI gate (GitHub Actions):

- Trigger: push/PR to `main`.
- Steps: install `requirements-dev.txt`, run `ruff check src tests scripts`, run `pytest -q`.

Promotion recommendation for current V1 baseline:

1. Keep `main` green (lint + tests).
2. Build image from tagged commit.
3. Run Alembic migrations (`alembic upgrade head`) in target environment.
4. Start API with required env vars.
5. Validate health and smoke-check key endpoints.

## 5) Rollback Approach (Current State)

- Application rollback: redeploy previously known-good image/commit.
- Data rollback: restore database backup/snapshot from platform backup process.
- Note: do not assume automatic safe downgrade for every schema change; prefer restore-based rollback for incidents involving data correctness.

## 6) Operational Checks Post-Deploy

- `GET /health` returns `200` and `{ "status": "ok" }`.
- OpenAPI/Swagger page loads (`/docs`).
- Core RFQ list endpoint responds: `GET /rfq-manager/v1/rfqs`.
- Logs show normal startup and no repeated DB connectivity errors.
