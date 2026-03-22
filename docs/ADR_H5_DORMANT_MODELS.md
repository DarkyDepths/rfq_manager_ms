# ADR H5 — Dormant Model Decisions

## Status
Accepted (H5)

## Scope
This ADR covers dormant/schema-present models in V1:
- `rfq_history`
- `rfq_stage_field_value`

## Current V1 Runtime Behavior
- RFQ lifecycle mutations are persisted in active operational tables (`rfq`, `rfq_stage`, `subtask`, `rfq_note`, `rfq_file`, `reminder`, ...).
- Request traceability exists via H3 request correlation IDs and request-scoped logs.
- Lifecycle integration visibility exists via H4 published events (`rfq.created`, `rfq.status_changed`, `rfq.deadline_changed`, `stage.advanced`).
- Stage-form state is currently read/written via `rfq_stage.captured_data`.
- No live controller/service write path currently persists rows into `rfq_history` or `rfq_stage_field_value`.

## Decision

### 1) `rfq_history`
Decision: **Keep intentionally dormant for V1**.

Rationale:
- No current V1 business flow requires dedicated persisted audit rows to satisfy API behavior.
- Existing V1 traceability is provided by DB state, request-correlated logs, and published lifecycle events.
- Activating now would add write-path complexity and policy decisions (event taxonomy/retention/query semantics) that are out of current V1 scope.

V1 statement:
- Persistent audit-trail table writes are **out of scope for V1**.

Future activation trigger:
- Explicit product/compliance requirement for immutable persisted audit history beyond logs/events.

### 2) `rfq_stage_field_value`
Decision: **Keep intentionally dormant for V1**.

Rationale:
- Current V1 source of truth for stage form data is `rfq_stage.captured_data`.
- Activating `rfq_stage_field_value` now would create duplicate/competing persistence semantics for the same data.
- No current V1 API behavior requires normalized per-field rows.

V1 statement:
- Stage form source of truth is **`rfq_stage.captured_data` only**.

Future activation trigger:
- Confirmed product/reporting/search requirement that materially needs normalized/queryable per-field rows with clear ownership semantics.

## Consequences
- Keep migration history and schema intact for both tables.
- Keep runtime/business flows unchanged for V1.
- Document dormant status explicitly in docs/code comments.
- Lock decision with behavior tests to prevent accidental activation ambiguity.
