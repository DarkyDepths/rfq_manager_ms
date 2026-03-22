# Known Limitations (V1 Release Baseline)

This document is the honest limitation view for the current release baseline.

## 1) Current Capability (What Exists)

- Service is demo-operable through Docker Compose with migration bootstrap and seed scenarios.
- API health endpoint exists (`/health`) and docs endpoint is available (`/docs`).
- Quality-gate verification exists via `python scripts/verify.py`.
- RFQ code allocation is atomic via database-backed per-prefix counters (`IF` / `IB`).

## 2) Known V1 Limitations

- Event bus publishing is not active; connector remains a V1 stub.
- `rfq_history` is schema-present but dormant in current business flows.
- `rfq_stage_field_value` is schema-present, while effective stage form payloads rely on `rfq_stage.captured_data` in V1.
- Observability baseline is intentionally minimal: request correlation IDs + HTTP-level Prometheus metrics only.
- No full tracing/export stack is included (no OpenTelemetry collector/exporter or external tracing vendor integration in this repo).
- Deployment baseline is Dockerfile + Docker Compose; no production orchestrator manifests are provided.

## 3) Integration Seams (Planned but Not Active)

- IAM seam is active for bearer-token auth resolution when bypass mode is disabled.
- Event seam: `EVENT_BUS_URL` and connector placeholders exist for future event publication.
- `JWT_SECRET` remains reserved for future expanded IAM/JWT workflows.
