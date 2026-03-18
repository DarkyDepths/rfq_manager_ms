# CLEANUP_PROGRESS

Last updated: 2026-03-18 (MG-01 migration authority established)
Repository: `rfq_manager_ms`
Execution mode: phase-ordered, verify-first, minimal-scope

## Execution Order (locked)
1. BR-01
2. FS-01
3. MG-01
4. LG-01
5. LG-02
6. LG-03 + LG-04
7. SC-01 + SC-02 + SC-03
8. MD-01 + LG-05
9. MD-02 + MD-03 + MD-04
10. TS-01 + TS-02 + TS-03
11. DC-01 + DC-02 + DC-03 + SD-01 + SD-02 + SD-03
12. IF-01 + IF-02 + IF-03 + IF-04

## Issue Matrix

| Issue ID | Title | Status | Summary of Work Done | Files Touched | Verification Result | Commit Hash | Notes / Remaining Risk |
|---|---|---|---|---|---|---|---|
| BR-01 | 6 unmerged branches — main is stale | RESOLVED | Merged `feature/regenerate-current-documentation` into `main` (contains full chain). Resolved one docs conflict conservatively by keeping archived implementation-plan file from branch tip. Fast-forwarded `develop` to updated `main` locally. Published dedicated PR source branch `chore/br-01-cleanup-baseline` to origin. | README.md; docs/archive/*; docs/*_current.*; src/*; tests/* | Verified by `git rev-list --left-right --count main...<branch>`: all six chain branches show `N 0` (main ahead, branch not ahead). Graph shows merge commit on `main`; `develop` ff-updated locally. | cb12441 | BR-01 baseline code is ready on `origin/chore/br-01-cleanup-baseline`. Automated PR creation from tooling is blocked by missing GitKraken/GitHub auth; PR URL prepared: `https://github.com/DarkyDepths/rfq_manager_ms/pull/new/chore/br-01-cleanup-baseline`. No FS-01+ work started. |
| FS-01 | File storage write/read path coherence | RESOLVED | Verified on merged `main` baseline with deterministic end-to-end round-trip: upload to stage, DB metadata persistence, physical file write, list, download, legacy `uploads/` prefix fallback, delete + post-delete download rejection. No production-code defect reproduced. Added focused FS-01 integration coverage. | tests/integration/test_fs01_file_roundtrip.py | `pytest tests/integration/test_fs01_file_roundtrip.py tests/unit/test_file_controller.py -q` → 9 passed. Upload/download/delete and missing-file 404 behavior all confirmed. | - | Verified in SQLite-backed automated flow with FastAPI endpoints and real controllers/datasources. Residual risk: did not execute against live PostgreSQL instance in this environment due DB connection encoding error in local `.env` runtime. |
| MG-01 | Alembic migrations are non-functional | RESOLVED | Added authoritative schema migration (`bc8fe52aaace`) superseding legacy no-op head (`phase2_filter_indexes`). New revision creates all 11 tables, 21 model-backed indexes, and the cyclic `rfq.current_stage_id -> rfq_stage.id` FK (PostgreSQL path + SQLite batch-compatible path). Updated seed bootstrap to use Alembic (`downgrade base`/`upgrade head`) instead of `Base.metadata.create_all/drop_all`. | migrations/versions/bc8fe52aaace_authoritative_schema_baseline.py; migrations/versions/phase2_filter_indexes.py; scripts/seed.py | Verified with clean DB flow: `alembic upgrade head` created full schema (11/11 expected tables, 0 missing, 0 extra; 21 non-auto indexes), `alembic downgrade base` succeeded, and `alembic upgrade head` succeeded again. `scripts/seed.py --scenario=minimal --reset` successfully runs through Alembic migrations before seeding. | - | Local direct PostgreSQL validation remains constrained in this environment (Docker engine unavailable; direct psycopg2 connect raises UnicodeDecodeError). Migration logic preserves PostgreSQL-native FK path and was validated structurally plus executable in clean disposable DB flow. |
| LG-01 | Missing RFQ status FSM enforcement | OPEN | Not started. | - | Pending | - | Depends on merged baseline stability. |
| LG-02 | Last-stage completion hardcodes Submitted | OPEN | Not started. | - | Pending | - | Execute after LG-01. |
| LG-03 | Skipped stages deflate RFQ progress | OPEN | Not started. | - | Pending | - | Execute with LG-04. |
| LG-04 | RFQ create relies on model default status | OPEN | Not started. | - | Pending | - | Execute with LG-03. |
| LG-05 | Date recalculation matches by name | OPEN | Not started. | - | Pending | - | Depends on MD-01. |
| LG-06 | RFQ code generation not atomic | OPEN | Not started. | - | Pending | - | P2; later in logic hardening. |
| SC-01 | `file_path` exposed in API responses | OPEN | Not started. | - | Pending | - | Must remove internal storage leakage. |
| SC-02 | Auth contract mismatch (open endpoints) | OPEN | Not started. | - | Pending | - | Must make V1 bypass explicit and honest. |
| SC-03 | Sort parameter allows arbitrary model fields | OPEN | Not started. | - | Pending | - | Add whitelist + clean 400 on invalid sort. |
| MD-01 | `rfq_stage.stage_template_id` missing | OPEN | Not started. | - | Pending | - | Required for robust date recalculation. |
| MD-02 | `rfq_history` docstring mismatch | OPEN | Not started. | - | Pending | - | Align docs to code reality. |
| MD-03 | `rfq_stage_field_value` docstring mismatch | OPEN | Not started. | - | Pending | - | Align docs to JSON `value` reality. |
| MD-04 | `Reminder.updated_at` missing | OPEN | Not started. | - | Pending | - | Requires schema migration. |
| TS-01 | `conftest.py` empty, fixtures missing | OPEN | Not started. | - | Pending | - | Repair shared setup. |
| TS-02 | Duplicate tests in root and unit folders | OPEN | Not started. | - | Pending | - | Deduplicate after fixture baseline. |
| TS-03 | Missing lifecycle test coverage | OPEN | Not started. | - | Pending | - | Add focused minimum coverage. |
| DC-01 | Endpoint numbering duplicated/gapped | OPEN | Not started. | - | Pending | - | Reconcile to unique sequential 1–31. |
| DC-02 | Connector docs overstate capabilities | OPEN | Not started. | - | Pending | - | Mark clearly as V1 stubs/placeholders. |
| DC-03 | `scripts/running_app` contradicts README | VERIFY | Not started; will verify after BR-01 merge. | - | Pending | - | Resolve by align-or-delete rule. |
| SD-01 | Seed assigns phantom `blocker_description` | OPEN | Not started. | - | Pending | - | Remove non-persisted attribute assignment. |
| SD-02 | Seed RFQ codes mismatch runtime format | OPEN | Not started. | - | Pending | - | Align with IF-/IB- semantics. |
| SD-03 | Terminal seeded RFQs keep current stage | OPEN | Not started. | - | Pending | - | Mirror runtime terminal semantics. |
| IF-01 | Missing Dockerfile | OPEN | Not started. | - | Pending | - | Add minimal production-sensible image. |
| IF-02 | Missing docker-compose.yml | OPEN | Not started. | - | Pending | - | Provide reproducible local startup. |
| IF-03 | Missing CI workflow | OPEN | Not started. | - | Pending | - | Add lint/test workflow on push/PR. |
| IF-04 | requirements mixes prod+dev deps | OPEN | Not started. | - | Pending | - | Split prod and dev requirements. |
