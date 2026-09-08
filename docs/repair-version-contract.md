# Repair version contract — implementation pending

## Observed integration gap

At d9915d8, ProductionEngine._start_run_locked only permits SCRIPT_APPROVED;
failed rendered runs/episodes remain in postproduction or QA review. The current
repair-plan endpoint only reads diagnostic tasks. No repair-version creation API
exists. Calling ordinary start or overwriting sealed exports is not a solution.

## Required dedicated operation

A user-confirmed local repair-version request must bind source run, exact repair
plan digest, output seal, approved script revision, requester, and a durable
idempotency key. Validate latest-run ownership, project/episode identity, archive
state, unchanged script, current seal and blocking tasks before any mutation.
Concurrent/stale requests cannot create competing active versions.

Create a separate run/package with explicit parent provenance. Preserve original
run status, media bytes, approvals, seal and QA reports. Reusing valid source
assets requires current authorization and hash validation. Do not copy final QA
PASS or generation/payment approvals into the new version. Do not blindly reset
episode state: add an explicit repository transaction/audit transition describing
the new active repair version and its approved-script lineage.

The preparation action must not submit provider work. New provider generation
requires the existing explicit per-task budget approval; repair retries must not
reuse an ambiguous old charge. Approved unchanged shots may be reused only by
verified reference, while failed shots are selected for replacement. Render a new
immutable master, then rerun structural, decoded, semantic and human QA before
separate controlled publication approval.

## Required tests and UI

- Exact retry/restart returns one repair version; changed request/key conflicts.
- Concurrent attempts create at most one active version.
- Stale plan/script/old source run, archived project and unrelated episode reject.
- Original master/seal/events remain unchanged; no inherited release approval.
- No provider request during preparation; replacement task has fresh budget gate.
- Actual encoded replacement renders to a distinct path and repeats all QA.
- Native explains the repair in plain language, asks one new-version confirmation,
  restores progress after restart, and never asks users to re-enter the story.

This document is a concrete implementation contract, not completion evidence.

## Initial implementation evidence

ProductionRunCreate now accepts an explicitly confirmed, parent/plan-bound local
repair request with mandatory idempotency key and no paid approval. Engine reuses
the established preflight/package transaction; repository rechecks latest parent,
QA state, script and archive state before atomically activating the new run.
The original run and files remain unchanged; new policy records repair lineage.

One public-API test passes (4.24s): failed structure QA → repair plan → distinct
local run → restart/exact replay → competing old-parent request rejected;
old files unchanged.12 existing authorization tests pass (6.20s). This is an
initial implementation, not the complete contract: native confirmation, concurrent
plan mutation/failure recovery, selective asset reuse and actual repaired master
acceptance remain required. No paid call or release occurred.

Follow-up transaction test: two cases pass (3.69s). In addition to exact replay,
the test changes the parent to CANCELLED after engine validation but before the
repository commit. The API rejects with 409, latest run remains the parent, and
all original files retain their bytes. This covers a status race, not concurrent
plan-file mutation or every recovery boundary. Missing confirmation/requester,
missing digest and inherited paid approval are rejected with 422; stale digest
is rejected with 409. CI for implementation 16abb58 is pending in run34270680499.
# Commit-boundary verification, 2026-09-08

At c37b289 the repository requires a repair-source validator while committing
the local preflight transaction. The engine rechecks the typed repair plan,
canonical digest, current output seal and expected plan digest. A plan corrupted
between initial validation and commit now rejects with409; no child run is
committed and parent output files are unchanged. This narrows the validation
window but does not claim a filesystem transaction or protection against arbitrary
out-of-process mutation after the check.

Executed: `.venv/bin/pytest tests/test_repair_versions.py
tests/test_production_authorization.py tests/test_interactive_story.py -q`:
22 passed in7.73s. Ruff on modified runtime files/tests passed. Fixtures only;
real repaired master, native repair confirmation and full CI remain required.
