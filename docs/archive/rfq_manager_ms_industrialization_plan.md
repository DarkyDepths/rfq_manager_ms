# rfq_manager_ms — Industrialization Plan

**Version:** 1.0
**Date:** March 2026
**Context:** Post-cleanup baseline. 28/29 cleanup issues resolved. Service is containerized with CI. This plan covers the transition from "clean demo-ready core" to "first deployable, supportable microservice."

---

## Current State (What Is Already Done)

Before defining what remains, here is what the cleanup phase already delivered — verified on `main` at commit `8f258e5`:

- **28/29 cleanup issues resolved** (only LG-06 deferred as P2)
- **Lifecycle FSM enforced** with tested transition map
- **4-revision Alembic migration chain** managing the full 11-table schema
- **File upload/download round-trip** verified with legacy path fallback
- **Auth bypass** explicitly documented, config-controlled, and logged at startup
- **file_path removed** from all API responses, replaced by `download_url`
- **Sort whitelist** enforced with clean 400 error
- **60+ passing tests** covering FSM, progress, file handling, auth bypass, seed consistency
- **Dockerfile** (python:3.11-slim, prod deps only)
- **docker-compose.yml** (postgres:16 + api with healthcheck, alembic on startup)
- **CI pipeline** (ruff lint + pytest on push/PR to main)
- **requirements split** (prod vs dev)
- **Seed data aligned** with runtime semantics (IF/IB codes, stage_template_id, terminal current_stage_id = NULL)
- **Route numbering** sequential 1–31 with full reference table in README
- **README** with Docker Compose quick start and manual setup

This is the baseline. Industrialization formalizes, proves, and hardens it — it does not rebuild it.

## Execution Status

- Stage 1 — Closure and Baseline Freeze: **Implemented** (pending/subject to PR merge validation)
- Stage 2 — Operational Readiness: **Not started**
- Stage 3 — Targeted Hardening: **Not started**

---

## What Industrialization Means Here

Turn the cleaned service into something that:

1. Someone other than the author can start, seed, verify, and operate
2. BACAB leadership can see running in a demo with confidence
3. The PFE jury can evaluate as a real engineering deliverable, not a prototype
4. Has a clear deployment approach and known limitations documented honestly

It is **not**: architecture redesign, feature expansion, IAM integration, intelligence work, or chatbot logic.

---

## Stage 1 — Closure and Baseline Freeze

**Goal:** Close the cleanup era formally. Create the reference point for all future work.

**Estimated effort:** 2–3 hours

### Deliverables

| # | Deliverable | Detail | Acceptance |
|---|-------------|--------|------------|
| 1.1 | Delete stale files | Remove: `scripts/audit_tests.py`, `scripts/audit_tests_2.py`, `tests/postman/test_trace.txt`, `tests/postman/test_trace_2.txt`, `src/utils/uuid.py`, `docs/archive/clean_yaml.py`, `docs/archive/fix_html.py`, `docs/archive/fix_yaml.py`, `docs/archive/rewrite_impl_plan.py`, `docs/archive/update_docs.py`, `docs/archive/package.json`, `docs/archive/package-lock.json` | `find` confirms zero dead files in those paths |
| 1.2 | Finalize env/config documentation | Add a config reference table to README listing every env var, whether required/optional, default value, and what it controls. Include `AUTH_BYPASS_ENABLED`, `FILE_STORAGE_PATH`, `DATABASE_URL`, `MAX_FILE_SIZE_MB`, `CORS_ORIGINS`, `JWT_SECRET`, `APP_ENV`, `APP_DEBUG`, `APP_PORT`, `IAM_SERVICE_URL`, `EVENT_BUS_URL`. | README has a "Configuration" section with a clear table |
| 1.3 | Add fail-fast on missing DATABASE_URL | If `DATABASE_URL` is not set, app should fail immediately at startup with a clear error message, not crash with a cryptic SQLAlchemy exception. | Start app without DATABASE_URL → clean error, not traceback |
| 1.4 | Tag baseline release | Create Git tag `v1.0.0` on main with an annotated message summarizing what's clean, what's deferred (LG-06), and what's out of scope (IAM, intelligence, chatbot). | `git tag -l` shows `v1.0.0`; tag message is a readable release note |
| 1.5 | Enable branch protection | On GitHub: require PR reviews for main, require CI status checks to pass before merge. | Settings → Branches → main protection rules active |
| 1.6 | Write release note | Short document (in repo as `RELEASE_v1.0.0.md` or in the tag): what this version contains, what was cleaned, what is intentionally deferred, what is out of scope. | File exists and is honest |

### Acceptance for Stage 1
- No dead/confusing files in the repo
- README has a config table someone can follow without asking the author
- App fails fast when misconfigured
- `v1.0.0` tag exists with a readable release note
- Branch protection prevents direct push to main

---

## Stage 2 — Operational Readiness

**Goal:** Produce the documents that make the service operable by someone other than the author.

**Estimated effort:** 1–2 days

### Deliverables

| # | Deliverable | Detail | Acceptance |
|---|-------------|--------|------------|
| 2.1 | Deployment approach note | One-page document for BACAB: "V1 deploys via Docker Compose on [target]. Here's how startup works, how migrations run, how config is injected." Define whether target is VM, container host, or cloud. Include rollback basics: "roll back = redeploy previous image + downgrade migration if needed." | Document exists, reviewed by boss, answers "how will we host this?" |
| 2.2 | Operational runbook | Markdown file (`docs/RUNBOOK.md`) with sections: How to start (docker compose up), How to seed demo data, How to run migrations manually, How to verify health, How to inspect logs (docker compose logs), How to reset demo data, Common issues and recovery. | A new developer can follow the runbook from zero to running API without asking the author |
| 2.3 | Architecture one-pager | Single document (for PFE jury + BACAB) showing: service boundary, layered architecture (routes→controllers→datasources→translators→models), 6 API resource families, 31 endpoints, 11 tables, tech stack, what's in scope vs out of scope, integration seams (IAM, event bus, intelligence). Use the BACAB architecture pattern as the reference. | One page that a jury member can read in 3 minutes and understand what the service does and how |
| 2.4 | Known limitations section | Either in README or a dedicated `docs/KNOWN_LIMITATIONS.md`: LG-06 (non-atomic code gen), auth bypass is V1-only, rfq_history/rfq_stage_field_value are dormant, event bus connector is a stub, no real IAM integration yet, no request correlation IDs, no metrics/monitoring. | Honest, concise, doesn't hide anything |

### Acceptance for Stage 2
- A developer who has never seen the repo can start it and run a demo by following the runbook
- BACAB bosses have a one-page deployment approach they can discuss
- PFE jury has an architecture one-pager that explains the service clearly
- Known limitations are documented, not hidden

---

## Stage 3 — Targeted Hardening

**Goal:** Close the one real technical debt item and create a demo-ready validation flow.

**Estimated effort:** 1 day

### Deliverables

| # | Deliverable | Detail | Acceptance |
|---|-------------|--------|------------|
| 3.1 | Fix LG-06: atomic RFQ code generation | Replace read-max-then-increment with either: (a) `SELECT ... FOR UPDATE` + retry on IntegrityError, or (b) a PostgreSQL sequence. Add a unit test that verifies uniqueness under simulated contention. | Two concurrent creates never produce the same code; unique constraint violation triggers retry, not 500 |
| 3.2 | Smoke/demo validation flow | A scripted walkthrough (shell script or Postman collection) that exercises the core lifecycle: create RFQ → list → get detail → advance through 2 stages → upload file → download file → create reminder → list reminders → update RFQ to terminal status. | Script runs end-to-end against a fresh `docker compose up` with seeded data and produces a clear pass/fail |
| 3.3 | Postman smoke collection | Export the smoke flow as a Postman collection (`tests/postman/rfq_manager_ms_smoke_v1.json`) with environment variables. This replaces the old `v1.1` collection which is stale. | Collection importable in Postman, runs against localhost:8000 with seeded data |
| 3.4 | Migration sanity in CI (optional) | Add a CI step that runs `alembic upgrade head` on a disposable SQLite DB to verify migration chain integrity on every push. | CI green after migration step; broken migration = CI red |

### Acceptance for Stage 3
- LG-06 is closed — 29/29 cleanup issues resolved
- A scripted smoke flow proves the service works end-to-end
- Postman collection exists for demo/regression
- CI optionally validates migration chain

---

## Deferred Backlog (Post-PFE / Post-V1)

These items are from the full A→K industrialization roadmap. They are legitimate but should not block the current milestone.

| Item | Why Deferred |
|------|-------------|
| Structured logging with JSON format | Useful for production, not needed for V1 demo or PFE defense |
| Request correlation ID middleware | Useful for distributed tracing, but no distributed system yet — single service |
| Prometheus/metrics endpoint | No monitoring infrastructure to consume metrics yet |
| Dependency vulnerability scan | Good practice, but not a V1 gate |
| Endpoint access level classification | Depends on rfq_iam_ms integration which is a separate workstream |
| Load/performance profiling | No production traffic to profile against yet |
| Changelog discipline / automated release notes | Valuable for a team, overkill for a single-author PFE |
| Coverage publishing in CI | Nice to have, not a quality gate for V1 |
| Kubernetes manifests / deployment strategy | Explicitly deferred until Docker/Compose is validated in a real environment |

These are tracked here so they are not forgotten, not so they are done now.

---

## What Bosses See as Outputs

At the end of this plan, the visible outputs are:

1. **A tagged baseline release** (`v1.0.0`) with a release note
2. **A green CI pipeline** that blocks broken PRs
3. **A one-command local startup** (`docker compose up --build`)
4. **A deployment approach note** that answers "how will we host this?"
5. **A smoke-test demo flow** that proves the service works
6. **A runbook** that lets someone else operate the service
7. **An architecture one-pager** for jury and management
8. **A known limitations list** that is honest about what's V1 and what's deferred
9. **Zero open cleanup debt** (29/29 resolved after LG-06)

---

## What Stays Out of Scope

To maintain discipline, the following are explicitly excluded from this industrialization phase:

- Architecture redesign of rfq_manager_ms
- Intelligence logic (rfq_intelligence_ms)
- Chatbot logic (rfq_chatbot_ms)
- Full IAM integration (rfq_iam_ms ownership)
- Frontend/UI work
- Multi-environment deployment automation
- Kubernetes orchestration
- Feature expansion beyond operational readiness

These remain separate platform concerns, sequenced after rfq_manager_ms is stable and deployed.

---

## Execution Timeline

| Stage | Duration | Depends On |
|-------|----------|------------|
| Stage 1 — Closure and baseline freeze | 2–3 hours | Nothing — start immediately |
| Stage 2 — Operational readiness | 1–2 days | Stage 1 complete |
| Stage 3 — Targeted hardening | 1 day | Stage 1 complete (can overlap with Stage 2) |

**Total: 3–4 days of focused work.**

---

*The full A→K industrialization roadmap remains as the internal strategic reference. This 3-stage plan is the execution version — scoped, sequenced, and achievable by one person before the PFE defense.*
