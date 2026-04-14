# Deployment Approach (Stage 2)

This document defines the current, implementation-true deployment approach for `rfq_manager_ms` V1.

## 1) Scope

- Covers how to run and promote the current API safely using the existing repository assets.
- Reflects current runtime behavior in `Dockerfile`, `docker-compose.scenario.yml`, `src/config/settings.py`, and `.github/workflows/ci.yml`.
- Does not introduce new platform architecture (Kubernetes, managed secrets, blue/green tooling, etc.).

## 2) Deployment Modes

### A. Local scenario stack (recommended for dev/QA validation)

Use the workspace scenario orchestrator to run the curated manager + intelligence demo stack:

```bash
python ../scripts/rfqmgmt_scenario_stack.py all --seed-set full
```

What this does:

- Starts the manager scenario compose file and its paired intelligence scenario stack.
- Runs curated scenario seeding instead of generic fake sample data.
- Exposes the manager API on `:18000` for local UI testing.

Stop stack:

```bash
python ../scripts/rfqmgmt_scenario_stack.py down --remove-volumes
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
- Steps: install `requirements-dev.txt`, then run `python scripts/verify.py`.
- Verifier includes: `ruff check src tests scripts`, `pytest -q`, and startup/import sanity (`create_app()`).

Promotion recommendation for current V1 baseline:

1. Keep `main` green (`python scripts/verify.py`).
2. Build image from tagged commit.
3. Run Alembic migrations (`alembic upgrade head`) in target environment.
4. Seed only base workflows/rules if the environment needs bootstrap metadata.
5. Do not run scenario fake RFQ seeders in production-like environments.
6. Start API with required env vars.
7. Validate health and smoke-check key endpoints.

## 5) Rollback Approach (Current State)

- Application rollback: redeploy previously known-good image/commit.
- Data rollback: restore database backup/snapshot from platform backup process.
- Note: do not assume automatic safe downgrade for every schema change; prefer restore-based rollback for incidents involving data correctness.

## 6) Operational Checks Post-Deploy

- `GET /health` returns `200` and `{ "status": "ok" }`.
- OpenAPI/Swagger page loads (`/docs`).
- Core RFQ list endpoint responds: `GET /rfq-manager/v1/rfqs`.
- Logs show normal startup and no repeated DB connectivity errors.
