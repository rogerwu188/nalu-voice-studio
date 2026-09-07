# Explicit preflight-to-production authorization

Checkpoint only; SOP-04/08/12 remain IN_PROGRESS. No provider call, payment,
generated video, native interaction or final release is claimed by this evidence.

## Core workflow defect

The native client starts dry runs. Image/video cost approval and submission require
a non-dry run, but starting a second run after preflight conflicts with the episode's
PREPRODUCTION state and loses the original plan's bindings. A cost button alone
therefore cannot connect confirmed scripts to actual production.

## Implemented boundary

`POST /v1/production-runs/{run_id}/production-authorization` takes the current
approved plan event/digest, immutable package digest, explicitly confirmed positive
episode budget, approver and confirmation, and guardian confirmation for children.
No default approval or automatic paid submission is introduced.

Under one SQLite writer lock it checks current run/plan/package/script/library,
rejects reservations, submissions (including uncertain attempts), remote bindings
and other downstream effects. Existing purely local image preparations may remain
as historical evidence, but cannot be reused against the changed plan/package.

It writes a separately hashed immutable package, materializes and preflights the
real vendored Qingshan workspace locally, then atomically switches the same run to
waiting_for_approval and appends the rebound approved plan. Original story, script,
plan, run ID and package bytes remain. Request-digest receipts support identical
concurrent/restart replay; a different budget cannot overwrite an existing approval.
Failure before commit retains the original context and reuses the deterministic
snapshot path on retry. Individual image/video reservations and dispatch gates
still apply. The amount is a local estimated budget, not a provider-enforced cap.

## Verification and remaining work

Tests use synthetic local scripts/plans and actual Qingshan materialization and
preflight, not live provider outputs. Cover promotion, original bytes, no second
run/provider binding, strict request validation, child guardian, web-origin denial,
stale plan, downstream locks, concurrent/restart replay, preflight failure/recovery,
and old/new image preparation bindings.

Local run: `pytest -q tests/test_production_authorization.py
tests/test_library_snapshot_refresh.py tests/test_image_budget.py
tests/test_goal_progress_audit.py`: **31 passed in 10.53s**. Ruff and `git diff
--check` passed; OpenAPI contract regenerated. These are checkpoint tests only.

Native authorization readback/action and budget/dispatch wiring remain required.
Current commit CI and native QA are not yet accepted. Prior native preparation
commit `040a149` CI was still running; reviewed-video `cb1c10d` completed CI run
[34081413828](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34081413828).
No full SOP status is promoted by this checkpoint.
