# Known Limitations (V1 Release Baseline)

This document is the honest limitation view for the current release baseline.

## 1) Current Capability (What Exists)

- Service is demo-operable through Docker Compose with migration bootstrap and seed scenarios.
- API health endpoint exists (`/health`) and docs endpoint is available (`/docs`).
- Quality-gate verification exists via `python scripts/verify.py`.
- RFQ code allocation is atomic via database-backed per-prefix counters (`IF` / `IB`).

## 2) Known V1 Limitations

- Event publication baseline is intentionally minimal (HTTP best-effort, post-commit) and is not yet a durable outbox/retry architecture.
- `rfq_history` is intentionally dormant in V1; persistent audit-table writes are deferred.
- `rfq_stage_field_value` is intentionally dormant in V1; stage form source of truth is `rfq_stage.captured_data`.
- Observability baseline is intentionally minimal: request correlation IDs + HTTP-level Prometheus metrics only.
- No full tracing/export stack is included (no OpenTelemetry collector/exporter or external tracing vendor integration in this repo).
- Deployment baseline is Dockerfile + Docker Compose; no production orchestrator manifests are provided.

## 3) Integration Seams (Planned but Not Active)

- IAM seam is active for bearer-token auth resolution when bypass mode is disabled.
- Event seam is active via `EVENT_BUS_URL` for H4 lifecycle publication (`rfq.created`, `rfq.status_changed`, `rfq.deadline_changed`, `stage.advanced`).
- `JWT_SECRET` remains reserved for future expanded IAM/JWT workflows.
