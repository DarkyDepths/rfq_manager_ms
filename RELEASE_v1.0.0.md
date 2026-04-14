# RELEASE v1.0.0

## Baseline status
rfq_manager_ms reaches a clean and supportable V1 baseline on top of completed cleanup + Stage 1 baseline-freeze work.

## What is clean/stable now
- Core API baseline is stabilized with 31 documented endpoints and aligned contracts.
- Migration chain is active and used by seed/startup flows.
- Local scenario-stack workflow exists (`Dockerfile`, `docker-compose.scenario.yml`, `../scripts/rfqmgmt_scenario_stack.py`).
- CI workflow runs lint + tests on push/PR to `main`.
- Seed/runtime semantics are aligned (codes, stage-template links, terminal-stage pointers).
- Scenario verification now reads manifest-declared anchor roles instead of duplicating seed assumptions in the stack script.
- Tracked workflow/docs truth is aligned with the live operational contract (no draft/submitted live statuses; short workflow = 6 stages).
- Stage 1 closure housekeeping completed (stale/dead files removed, config docs finalized, DB fail-fast added).

## Cleanup/industrialization baseline completed
- Cleanup phases are closed at baseline level.
- Industrialization Stage 1 (Closure and Baseline Freeze) is completed in code/docs scope.

## Intentionally deferred
- **LG-06**: RFQ code generation is still non-atomic under high concurrency and remains a hardening follow-up item.

## Explicitly out of scope for v1.0.0
- Full IAM integration and production auth enforcement
- Intelligence logic
- Chatbot logic
- Frontend/UI work
- Major feature expansion

## Branch protection (admin action, not code)
Recommended `main` protection settings:
1. Require a pull request before merging
2. Require at least 1 approving review
3. Require status checks to pass before merging
4. Required check: **CI / lint-and-test** (from `.github/workflows/ci.yml`)

These are repository settings and must be enabled by a maintainer/admin in GitHub.

## Baseline tag guidance
Tagging is an operational release step and should be applied on the approved baseline commit.

Suggested annotated tag commands:

```bash
git checkout main
git pull origin main
git tag -a v1.0.0 -m "v1.0.0 baseline freeze: cleanup complete except deferred LG-06; industrialization Stage 1 complete"
git push origin v1.0.0
```
