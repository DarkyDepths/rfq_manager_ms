# Known Limitations (Stage 2)

This list documents current V1 limitations to set clear operational expectations.

## 1) Authentication and Authorization

- V1 currently supports auth bypass mode (`AUTH_BYPASS_ENABLED`), which injects a deterministic demo user context.
- IAM connector remains a placeholder seam; no active `rfq_iam_ms` enforcement path is wired yet.

## 2) External Integrations

- Event bus connector is a placeholder; outbound event publishing is not active.
- Reminder “test email” endpoint is log-only in V1; no real email transport is configured.

## 3) Reminder Automation Model

- Due-reminder execution is currently on-demand via API endpoint (`/reminders/process`).
- No built-in scheduler/worker process is defined in the repository for periodic automatic execution.
- Daily send cadence and max-send gate are enforced by current service logic.

## 4) Storage and Environment Assumptions

- File storage defaults to local filesystem (`FILE_STORAGE_PATH` / `./uploads`).
- Cloud object storage integration is not active in current V1 implementation.
- Deployment assets are baseline-focused (Dockerfile + Compose) and do not include production orchestration manifests.

## 5) Observability and Ops Tooling

- Health check exists (`/health`), but no built-in metrics/tracing stack is included.
- Operational insight is mainly from API responses and application logs.

## 6) Schema and Feature Maturity

- `rfq_history` and `rfq_stage_field_value` are present at schema level but dormant in V1 business flows.
- `JWT_SECRET`, `IAM_SERVICE_URL`, and `EVENT_BUS_URL` are reserved configuration seams and not fully exercised end-to-end in current V1 behavior.
