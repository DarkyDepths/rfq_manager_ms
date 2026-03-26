# rfq_manager_ms — Pre-Industrialization Cleanup Plan

**Dual-LLM code review · March 2026 · v2 (post-feedback) · 29 issues · 9 phases**

---

## Executive Summary

Two independent LLM reviews converged on the same conclusion: the rfq_manager_ms codebase is architecturally sound but not ready for industrialization. The layered architecture (routes → controllers → datasources → translators → models) follows BACAB patterns correctly, dependency injection is clean, and the domain logic for RFQ lifecycle management is functional.

This plan identifies **29 concrete issues** across **9 phases**. The three P0 blockers are: stale main branch, non-functional Alembic migrations, and missing RFQ status FSM. Each phase includes acceptance criteria that define "done."

---

## What Changed in v2

Based on stakeholder feedback, five corrections were applied to the original plan:

- **Count reconciled:** Title and body now consistently report 29 issues.
- **Post-merge revalidation:** Each issue carries a merge status tag (`OPEN` / `VERIFY` / `RESOLVED`) indicating whether it survives the branch merge or needs re-checking on merged main.
- **Auth gap added:** SC-02 now explicitly tracks the gap between the contract's declared bearer auth and the actual open endpoints, with a pragmatic V1 bypass strategy.
- **stage_template_id reordered:** MD-01 is important but no longer blocks the critical path. It sits in Phase 4, after FSM and semantics are locked.
- **Acceptance criteria added:** Every phase now has a concrete "done means" statement that can be verified in under 2 minutes.

---

## Legend

### Priority Tags

| Tag | Meaning | Rule |
|-----|---------|------|
| **`P0`** | Blocker | System is broken without this. Must fix before any demo or merge. |
| **`P1`** | High | Must fix before PFE defense or BACAB handoff. Logic or contract violation. |
| **`P2`** | Medium | Should fix for code quality. Jury won't catch it, but a senior dev would. |

### Post-Merge Status

| Tag | Meaning |
|-----|---------|
| **`OPEN`** | Confirmed present on all branches — survives merge. |
| **`VERIFY`** | May be fixed by the branch merge — re-check on merged main. |
| **`RESOLVED`** | Fixed on branch chain — will close on merge. |

---

## Phase Summary with Acceptance Criteria

| Phase | # | P0 | P1 | P2 | Effort | Done Means |
|-------|---|----|----|-----|--------|------------|
| 0 — Branch Hygiene (Do First) | 1 | 1 | – | – | 30 min | main branch contains all 6 branch-chain commits. `git log main` shows repo-hygiene through regenerate-current-documentation. Stale branches deleted. develop tracks main. |
| 1 — Breaking Bugs (Fix Before Demo) | 2 | 2 | – | – | 2 hours | `alembic upgrade head` on an empty database creates all 11 tables with correct indexes. Upload a file to a stage, then download it via `/files/{id}/download` — round-trip succeeds. |
| 2 — Logic Gaps (Correct Before PFE) | 6 | 2 | 3 | 1 | 4 hours | `PATCH /rfqs/{id}` with status='Draft' when current status is 'Submitted' returns 409. Completing the last stage does NOT auto-set status to 'Submitted'. An RFQ with 5 completed + 5 skipped stages shows 100% progress. RFQ create explicitly sets status='In preparation' (visible in code, not relying on default). |
| 3 — Security & API Surface | 3 | – | 2 | 1 | 2 hours | GET stage detail response has no `file_path` field — only `download_url`. App startup logs 'V1: auth bypassed'. Sort query with `?sort=workflow_id` returns 400. |
| 4 — Model / Schema Alignment | 4 | – | 1 | 3 | 3 hours | `rfq_stage` table has `stage_template_id` column (verified via `\d rfq_stage` in psql). All model docstrings match their actual column definitions. Reminder model has `updated_at`. |
| 5 — Test Suite | 3 | – | 2 | 1 | 4 hours | `pytest` runs without import errors. No duplicate test files in `tests/` root. `conftest.py` provides working `db_session` and `test_client` fixtures. At least one test covers `rfq_controller.create()` and one covers a terminal state transition. |
| 6 — Documentation | 3 | – | 1 | 2 | 2 hours | Every endpoint in route files has a unique sequential number 1–31. Connector docstrings say 'V1 stub'. `scripts/running_app` either matches README or is deleted. |
| 7 — Seed Data Realism | 3 | – | 1 | 2 | 1 hour | `python scripts/seed.py --scenario=demo --reset` runs without warnings. Seeded RFQ codes start with IF-/IB-. Terminal RFQs have `current_stage_id = NULL`. No phantom attributes set on models. |
| 8 — Infrastructure | 4 | – | 2 | 2 | 3 hours | `docker compose up` starts postgres + api. API responds to `/health`. `pip install -r requirements.txt` does not install pytest or Faker. GitHub push triggers CI lint + test. |

**Total estimated effort: ~21.5 hours. Critical path (Phases 0–2): ~6.5 hours.**

---

## Detailed Issue Registry

---

### Phase 0 — Branch Hygiene (Do First)

> **Acceptance:** main branch contains all 6 branch-chain commits. `git log main` shows repo-hygiene through regenerate-current-documentation. Stale branches deleted. develop tracks main.

#### BR-01 · 6 unmerged branches — main is stale

| | |
|---|---|
| **Priority** | `P0` |
| **Merge Status** | `OPEN` |
| **Category** | Git |
| **Problem** | Chain: repo-hygiene → normalize-db-config → normalize-file-storage-paths → enforce-subtask-progress-ownership → align-documentation-truth → regenerate-current-documentation. Fixes and regenerated docs live only on branches. |
| **Fix** | Squash-merge the full chain into main via a single PR. Delete stale branches after merge. Verify develop tracks main. |
| **Files** | Git branches (no source file) |

---

### Phase 1 — Breaking Bugs (Fix Before Demo)

> **Acceptance:** `alembic upgrade head` on an empty database creates all 11 tables with correct indexes. Upload a file to a stage, then download it via `/files/{id}/download` — round-trip succeeds.

#### MG-01 · Alembic migrations are non-functional

| | |
|---|---|
| **Priority** | `P0` |
| **Merge Status** | `OPEN` |
| **Category** | Infra |
| **Problem** | Only migration (phase2_filter_indexes) has empty `upgrade()`/`downgrade()`. No initial migration. Schema is created only by seed.py's `Base.metadata.create_all()`. Running `alembic upgrade head` on an empty DB creates zero tables. |
| **Fix** | Generate a proper initial migration with `alembic revision --autogenerate`. Make phase2_filter_indexes actually create the declared indexes. Seed.py should run `alembic upgrade head` internally instead of `create_all()`. |
| **Files** | `migrations/versions/*.py`, `scripts/seed.py` |

#### FS-01 · File storage write/read path coherence

| | |
|---|---|
| **Priority** | `P0` |
| **Merge Status** | `VERIFY` |
| **Category** | Controller |
| **Problem** | On older main: upload wrote to `FILE_STORAGE_PATH/rfq_id/stage_id/` but stored a relative POSIX path, while download used `_resolve_physical_path` with a legacy 'uploads/' prefix strip. The branch chain normalized this. After merge, need to verify the upload → store → download round-trip actually works end-to-end. |
| **Fix** | After merging BR-01: create an RFQ, upload a file, download it. If round-trip works, mark resolved. If not, trace the mismatch between stored path and `_resolve_physical_path` logic. |
| **Files** | `src/controllers/rfq_stage_controller.py`, `src/controllers/file_controller.py` |

---

### Phase 2 — Logic Gaps (Correct Before PFE)

> **Acceptance:** `PATCH /rfqs/{id}` with status='Draft' when current status is 'Submitted' returns 409. Completing the last stage does NOT auto-set status to 'Submitted'. An RFQ with 5 completed + 5 skipped stages shows 100% progress. RFQ create explicitly sets status='In preparation' (visible in code, not relying on default).

#### LG-01 · No RFQ status FSM — invalid transitions allowed

| | |
|---|---|
| **Priority** | `P0` |
| **Merge Status** | `OPEN` |
| **Category** | Controller |
| **Problem** | Only terminal→terminal is blocked (409). Nothing prevents Submitted→Draft, In preparation→Awarded, etc. The lifecycle (Draft → In preparation → Submitted → Awarded/Lost/Cancelled) is enforced only by convention, not code. |
| **Fix** | Add a `VALID_TRANSITIONS` dict in `rfq_controller.py` mapping each status to its allowed next states. Validate every status change in `update()` against this map. Return 409 Conflict for invalid transitions. |
| **Files** | `src/controllers/rfq_controller.py` |

#### LG-02 · Last stage completion hardcodes status='Submitted'

| | |
|---|---|
| **Priority** | `P0` |
| **Merge Status** | `OPEN` |
| **Category** | Controller |
| **Problem** | In `advance()`, when no next stage exists, `rfq.status` is set to 'Submitted'. But GHI workflows end with 'Award / Lost' stage — completing it semantically means the lifecycle is done, not that the offer was just submitted. |
| **Fix** | Remove the hardcoded 'Submitted' assignment. When last stage completes, either: (a) leave RFQ status unchanged and let the user explicitly set the terminal outcome, or (b) set status based on stage name heuristic with a fallback. Option (a) is safer and more honest. |
| **Files** | `src/controllers/rfq_stage_controller.py` |

#### LG-03 · Skipped stages deflate RFQ progress calculation

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Controller |
| **Problem** | `_update_rfq_progress` averages all stages including Skipped (progress=0). An RFQ with 10 stages where 5 are completed and 5 skipped shows 50% instead of 100%. |
| **Fix** | Exclude Skipped stages from the average. If all non-skipped stages are complete, set progress to 100. Same fix needed in `rfq_controller._update_rfq_progress` (update flow) and `rfq_stage_controller._update_rfq_progress` (advance flow). |
| **Files** | `src/controllers/rfq_stage_controller.py`, `src/controllers/rfq_controller.py` |

#### LG-04 · RFQ create relies on model default for status

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Controller |
| **Problem** | No explicit `rfq.status = 'In preparation'` in create flow. Relies on `Column(default='In preparation')`. If someone changes the model default, create silently produces wrong initial status. |
| **Fix** | Set `rfq_data['status'] = 'In preparation'` explicitly in `rfq_controller.create()` after building the rfq_data dict from the translator. |
| **Files** | `src/controllers/rfq_controller.py` |

#### LG-05 · Stage date recalculation matches by name, not template ID

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Controller |
| **Problem** | `_recalculate_stage_dates` finds template durations via `t.name == stage.name`. If two stages share a name, the wrong duration is used. Root cause: rfq_stage model is missing `stage_template_id` (see MD-01). |
| **Fix** | Depends on MD-01 (add `stage_template_id`). Once available, match by `stage.stage_template_id == template.id` instead of name. Interim: add a comment documenting the limitation. |
| **Files** | `src/controllers/rfq_controller.py` |

#### LG-06 · RFQ code generation is not atomic

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Datasource |
| **Problem** | `get_next_code` reads max code then increments. Two concurrent creates can get the same code. The unique constraint catches it as a 500 error with no retry. |
| **Fix** | Wrap in a `SELECT ... FOR UPDATE` or use a DB sequence. Add retry logic (up to 3 attempts) on `IntegrityError` from the unique constraint violation. |
| **Files** | `src/datasources/rfq_datasource.py` |

---

### Phase 3 — Security & API Surface

> **Acceptance:** GET stage detail response has no `file_path` field — only `download_url`. App startup logs 'V1: auth bypassed'. Sort query with `?sort=workflow_id` returns 400.

#### SC-01 · file_path exposed in API responses

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Translator |
| **Problem** | `StageFileResponse` returns the internal storage path (`rfq_id/stage_id/uuid_filename.xlsx`). Leaks server directory structure to any API consumer. |
| **Fix** | Remove `file_path` from `StageFileResponse`. Add a computed `download_url` field that returns `/rfq-manager/v1/files/{id}/download`. |
| **Files** | `src/translators/rfq_stage_translator.py`, `src/translators/file_translator.py` |

#### SC-02 · No authentication — contract declares bearer auth, endpoints are open

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Route/Infra |
| **Problem** | The V1 API contract and OpenAPI spec declare JWT bearer authentication via `rfq_iam_ms`. In reality, every endpoint is wide open. The IAM connector is an empty stub. `user_name` and `created_by` default to 'System' everywhere. |
| **Fix** | For V1 demo: add a documented bypass middleware that sets a hardcoded user context (name, team) from a config flag. Add a clear comment: 'V1: auth bypassed, see rfq_iam_ms integration plan.' This makes the gap explicit and traceable without blocking the demo. |
| **Files** | `src/app.py`, `src/connectors/iam_service.py` |

#### SC-03 · Sort parameter accepts any model column

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Datasource |
| **Problem** | `rfq_datasource.list()` uses `getattr(RFQ, column_name)` — allows sorting by internal fields like `workflow_id`, `current_stage_id`. |
| **Fix** | Add a `SORTABLE_FIELDS` whitelist: `{name, client, deadline, created_at, priority, status, progress, owner}`. Reject others with `BadRequestError`. |
| **Files** | `src/datasources/rfq_datasource.py` |

---

### Phase 4 — Model / Schema Alignment

> **Acceptance:** `rfq_stage` table has `stage_template_id` column (verified via `\d rfq_stage` in psql). All model docstrings match their actual column definitions. Reminder model has `updated_at`.

#### MD-01 · rfq_stage missing stage_template_id column (contract violation)

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Model |
| **Problem** | API contract V1 explicitly defines `stage_template_id` as FK → `stage_template` on `rfq_stage`. The actual SQLAlchemy model never implemented it. This breaks contract traceability and forces the name-based matching in LG-05. |
| **Fix** | Add `stage_template_id = Column(UUID, ForeignKey('stage_template.id'), nullable=True)` to `RFQStage`. Populate it during stage creation in `rfq_controller.create()`. Create Alembic migration for the new column. |
| **Files** | `src/models/rfq_stage.py`, `src/controllers/rfq_controller.py`, `migrations/` |

#### MD-02 · rfq_history docstring/column mismatch + completely dormant

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Model |
| **Problem** | Docstring says 'changed_by' column exists; model has `user_id` + `user_name`. Also, nothing anywhere writes to this table — zero audit trail. |
| **Fix** | Fix docstring to match actual columns. Add a TODO comment with the activation plan. Consider adding basic history writes for status changes and stage advances as a V1 stretch goal. |
| **Files** | `src/models/rfq_history.py` |

#### MD-03 · rfq_stage_field_value docstring/column mismatch

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Model |
| **Problem** | Docstring says 'field_value TEXT' but code has `value = Column(JSON)`. Both name and type differ from docs. |
| **Fix** | Align docstring with actual code. The JSON type is the correct choice — update the docstring to reflect reality. |
| **Files** | `src/models/rfq_stage_field_value.py` |

#### MD-04 · Reminder model has no updated_at

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Model |
| **Problem** | Every other mutable entity (RFQ, RFQStage, Subtask) has `updated_at`. Reminder doesn't, so you can't tell when a reminder was last modified. |
| **Fix** | Add `updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())`. Create Alembic migration. |
| **Files** | `src/models/reminder.py`, `migrations/` |

---

### Phase 5 — Test Suite

> **Acceptance:** `pytest` runs without import errors. No duplicate test files in `tests/` root. `conftest.py` provides working `db_session` and `test_client` fixtures. At least one test covers `rfq_controller.create()` and one covers a terminal state transition.

#### TS-01 · conftest.py is empty — no shared test fixtures

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Tests |
| **Problem** | Docstring describes fixtures (`db_session`, `test_client`, `sample_rfq`, `auth_headers`) but contains zero actual code. Every test file creates ad-hoc mocks independently. |
| **Fix** | Implement the described fixtures: SQLite in-memory session with `Base.metadata.create_all`, `TestClient` with dependency overrides, factory fixtures for Workflow+StageTemplate, RFQ, RFQStage. |
| **Files** | `tests/conftest.py` |

#### TS-02 · Duplicate test files between tests/ root and tests/unit/

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Tests |
| **Problem** | `test_rfq_controller.py`, `test_pagination.py`, `test_notification_service.py` exist in both locations with identical content. Confuses pytest and inflates apparent coverage. |
| **Fix** | Delete the root-level duplicates (`tests/test_*.py`). Keep only the `tests/unit/` versions. Verify `pytest.ini` testpaths covers `tests/unit/` and `tests/integration/`. |
| **Files** | `tests/test_rfq_controller.py`, `tests/test_pagination.py`, `tests/test_notification_service.py` |

#### TS-03 · No test coverage for RFQ create, terminal transitions, reminder CRUD

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Tests |
| **Problem** | `rfq_controller.create()` (the most complex method: stage generation, date calculation, code generation) has zero tests. Same for terminal state transitions and reminder create/list/stats. |
| **Fix** | Add unit tests for: `create()` happy path + edge cases (empty workflow, skip_stages, stage_overrides), terminal transitions (Awarded/Lost/Cancelled), reminder CRUD, and the FSM once LG-01 is implemented. |
| **Files** | `tests/unit/test_rfq_controller.py`, `tests/unit/test_reminder_controller.py` (new) |

---

### Phase 6 — Documentation

> **Acceptance:** Every endpoint in route files has a unique sequential number 1–31. Connector docstrings say 'V1 stub'. `scripts/running_app` either matches README or is deleted.

#### DC-01 · Route numbering has duplicates (#26 used twice) and gaps

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Docs |
| **Problem** | Reminder `/process` and stage file listing both claim endpoint #26. Original contract had 28; repo has 31 but numbering was never reconciled. |
| **Fix** | Re-number all endpoint comments sequentially 1–31 across route files. Add a single reference table in README mapping number → method → path → resource. |
| **Files** | `src/routes/*.py`, `README.md` |

#### DC-02 · Connector docstrings overstate capabilities

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Docs |
| **Problem** | `event_bus.py` and `iam_service.py` docstrings describe full functionality (JWT validation, event publishing). Files are completely empty — not even a class definition. |
| **Fix** | Rewrite docstrings to: 'V1 stub — placeholder for inter-service integration. No implementation. See rfq_communication_ms / rfq_iam_ms architecture briefs.' |
| **Files** | `src/connectors/event_bus.py`, `src/connectors/iam_service.py` |

#### DC-03 · scripts/running_app contradicts README

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `VERIFY` |
| **Category** | Docs |
| **Problem** | Uses port 5555, postgres:15, psycopg driver vs README's port 5432, postgres:16, psycopg2. After branch merge, README may be updated — verify. |
| **Fix** | After merge: if `running_app` is still contradictory, either update it to match README or delete it entirely. |
| **Files** | `scripts/running_app` |

---

### Phase 7 — Seed Data Realism

> **Acceptance:** `python scripts/seed.py --scenario=demo --reset` runs without warnings. Seeded RFQ codes start with IF-/IB-. Terminal RFQs have `current_stage_id = NULL`. No phantom attributes set on models.

#### SD-01 · Seed sets non-existent blocker_description attribute

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Seed |
| **Problem** | `seed.py`: `cur_stage.blocker_description = fake.sentence()`. `RFQStage` has no such column. SQLAlchemy silently assigns a Python attr without persisting it. |
| **Fix** | Remove the line. If the field is needed, add it to the model first. |
| **Files** | `scripts/seed.py` |

#### SD-02 · Seed RFQ codes ('GHI-XXXXX') don't match runtime format ('IF-XXXX' / 'IB-XXXX')

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Seed |
| **Problem** | Demo data uses a different code format than what the live system generates. Creates confusion during BACAB demo. |
| **Fix** | Change seed to use `rfq_datasource.get_next_code('IF')` or generate IF-/IB- prefixed codes directly. |
| **Files** | `scripts/seed.py` |

#### SD-03 · Terminal RFQs in seed keep current_stage_id populated

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Seed |
| **Problem** | Live controller logic sets `current_stage_id = None` on terminal transitions. Seeded Awarded/Lost RFQs keep it pointing to last stage, creating inconsistent demo data. |
| **Fix** | Set `rfq.current_stage_id = None` for Awarded/Lost/Cancelled RFQs in the seed, mirroring controller behavior. |
| **Files** | `scripts/seed.py` |

---

### Phase 8 — Infrastructure

> **Acceptance:** `docker compose up` starts postgres + api. API responds to `/health`. `pip install -r requirements.txt` does not install pytest or Faker. GitHub push triggers CI lint + test.

#### IF-01 · No Dockerfile

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Infra |
| **Problem** | No containerization for the application. Only Docker usage is postgres in dev. |
| **Fix** | Create a multi-stage Dockerfile: `python:3.11-slim`, copy requirements, pip install, copy src/, `CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]`. |
| **Files** | `Dockerfile` (new) |

#### IF-02 · No docker-compose.yml

| | |
|---|---|
| **Priority** | `P1` |
| **Merge Status** | `OPEN` |
| **Category** | Infra |
| **Problem** | No single-command dev environment. README has 11 manual steps. |
| **Fix** | Create `docker-compose.yml`: postgres service (postgres:16) + api service (build .). Set `DATABASE_URL`, mount volumes, expose 8000. |
| **Files** | `docker-compose.yml` (new) |

#### IF-03 · No CI/CD pipeline

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Infra |
| **Problem** | No GitHub Actions. No automated lint/test on push or PR. |
| **Fix** | Create `.github/workflows/ci.yml`: checkout, setup-python 3.11, pip install, ruff check, pytest. Trigger on push to main and PRs to main. |
| **Files** | `.github/workflows/ci.yml` (new) |

#### IF-04 · requirements.txt mixes prod and dev dependencies

| | |
|---|---|
| **Priority** | `P2` |
| **Merge Status** | `OPEN` |
| **Category** | Infra |
| **Problem** | Faker, pytest, pytest-asyncio sit alongside FastAPI and SQLAlchemy. No separation. |
| **Fix** | Split: `requirements.txt` (prod only), `requirements-dev.txt` (`-r requirements.txt` + test/dev deps). |
| **Files** | `requirements.txt`, `requirements-dev.txt` (new) |

---

## Execution Sequence

This order minimizes rework. Each step builds on a stable foundation from the previous one.

| # | Issues | Action | Gate (Done Means) | Why This Order |
|---|--------|--------|-------------------|----------------|
| 1 | BR-01 | Merge branch chain into main | `git log main` shows all 6 commits | Everything else targets the wrong baseline without this. |
| 2 | — | Smoke test merged main | Manual Postman pass: 0 failures | Verify create, list, detail, advance, upload/download, reminder, export all work. |
| 3 | FS-01 | Verify file upload/download round-trip | Upload + download returns identical file | Branch may have fixed this; confirm on merged main. |
| 4 | MG-01 | Create real Alembic initial migration | `alembic upgrade head` on empty DB creates 11 tables | Schema must be migration-managed before any model changes. |
| 5 | LG-01 | Implement RFQ status FSM | Invalid transition returns 409 | Core business rule. All downstream logic depends on valid transitions. |
| 6 | LG-02 | Fix last-stage completion semantics | Last stage advance does NOT auto-set Submitted | Depends on FSM being in place. |
| 7 | LG-03, LG-04 | Fix Skipped-stage progress + explicit create status | Skipped stages excluded from avg; create sets explicit status | Quick wins after FSM is locked. |
| 8 | SC-01, SC-02, SC-03 | API surface cleanup: file_path, auth bypass, sort whitelist | No file_path in responses; auth bypass logged; bad sort = 400 | Harden the public interface. |
| 9 | MD-01, LG-05 | Add stage_template_id + fix date recalculation | `rfq_stage` has `stage_template_id`; recalc uses ID not name | Contract alignment. Unlocks proper template matching. |
| 10 | MD-02–04 | Fix remaining model docstrings + add Reminder updated_at | All docstrings match code; Reminder has `updated_at` | Schema truth. |
| 11 | TS-01–03 | Fix conftest, dedup tests, add coverage | pytest runs clean; no duplicate files; `create()` has a test | Tests validate everything above. |
| 12 | DC-01–03, SD-01–03 | Fix docs, route numbering, seed realism | Unique numbering 1-31; seed codes are IF-/IB-; no phantom attrs | Polish layer. |
| 13 | IF-01–04 | Add Dockerfile, docker-compose, CI, split requirements | `docker compose up` starts working API | Packaging for deployment. |

---

*This document is a working backlog. Cross off issues as resolved.* **Start with step 1 — everything else depends on it.**
