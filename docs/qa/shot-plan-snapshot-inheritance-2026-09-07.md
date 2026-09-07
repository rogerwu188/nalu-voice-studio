# Approved shot-plan inheritance after character confirmation

Status: IN_PROGRESS; backend checkpoint, not full product or native acceptance.

The production package predates character cards derived from a shot plan. Newly
confirmed characters therefore do not appear in its sealed catalog. This change
adds `POST /v1/production-runs/{run_id}/shot-plan-inheritance` for an explicitly
prepared replacement snapshot. It does not mutate either package file, create
another run, invoke a model, copy provider tasks, or grant spending permission.

Requirements enforced inside one SQLite write transaction:

- Source and current target are distinct preflight runs for the same episode.
- Immutable package integrity is checked; all fields except the confirmed library
  and package digest must match exactly. Script, assets, continuity and spending
  policy differences block automatic inheritance.
- Target library matches the current confirmed repository catalog.
- Source event/hash identify its latest intact approved plan; approved script
  revision/content and episode duration are checked against current records.
- Any downstream event outside the explicit creative/preflight allowlist or
  remote task binding prevents copying work to a second run.
- Existing target creative work cannot be overwritten. Identical concurrent or
  restarted requests return the same event; no duplicate creative tasks.
- Preserved plan/director content and original confirmation provenance bind to
  the target package. `paid_approved` and `generation_performed` stay false.

Evidence: `tests/test_shot_plan_inheritance.py` uses synthetic local packages,
real SQLite and public character-confirmation API. Covers successful/restarted
and concurrent replay, changed script/assets/policy/continuity, stale library,
stale approval, tampering, downstream preparation, existing target plan, wrong
hash and browser-origin rejection. Related planning/library suite, including
concurrent replay: 35 tests passed in 12.62 seconds. Ruff, OpenAPI backward
compatibility and diff checks passed. No provider calls or real media generated.

Update: [same-run snapshot refresh](library-snapshot-refresh-2026-09-07.md)
now supplies materialization/preflight and atomic package/plan handover without
creating a replacement run. Native orchestration remains unfinished. The original
design constraint below explains why ordinary run creation must not be reused.

Original gap: replacement-run materialization/preflight and native orchestration
must be implemented before this endpoint is user-reachable. The existing run
creation path requires SCRIPT_APPROVED, while a successful initial preflight
moves the episode to PREPRODUCTION. Do not reset the episode state or silently
overwrite its package to work around this. A dedicated durable refresh operation
must preserve the original approved episode snapshot, atomically hand over current
run authority, and recover interrupted local materialization without new tasks.

Actual native UI/real source-to-master/release acceptance remains pending.
