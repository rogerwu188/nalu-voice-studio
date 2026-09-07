# Video cost/submission/recovery bridge

Checkpoint, not a finished native production journey. No real provider request
or charge was made for this work.

## Changes

- Native RuntimeClient now has separate typed methods to reserve the exact video
  cost, explicitly submit that reservation with the existing provider key, and
  observe its saved submission **without a key or submission POST**.
- Reservation responses must match run, preparation digest, quote, estimate,
  confirmed run budget and guardian flag; they cannot claim generation. Submission
  observations must match the reservation's run/task/request digest. HTTP success
  alone is insufficient.
- Added GET `/v1/production-runs/{run_id}/video-reservations/{reservation_id}/submission`.
  It validates durable reservation integrity and task/request binding, then reads
  SQLite only. It returns null before any binding exists, or the saved state,
  including ambiguous charge. It neither polls the provider nor retries production.
- Dispatch reuses the same binding validation. Browser-origin requests cannot
  create video cost approvals; existing runtime ownership checks still apply.

## Evidence

- `pytest -q tests/test_paid_submitter_boundary.py tests/test_video_pricing.py
  tests/test_goal_progress_audit.py`: **97 passed in 20.82s**.
- Added GET recovery assertions to all relevant dispatch cases: no pre-submit
  provider call, wrong-run rejection, accepted/uncertain receipt observation,
  runtime restart without a new call. Existing concurrency, changed context and
  single-attempt tests remain.
- Native tests added for distinct reserve/submit/observe HTTP methods, key header
  only at explicit dispatch, absent observations, unknown results, changed estimate
  and foreign-task rejection. Current native CI must run these tests.
- Ruff, OpenAPI regeneration and diff checks passed.
- Prior `340c440` CI [34083297991](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34083297991)
  had completed ARM macOS native tests/build/bundle verification successfully at
  observation; this does not prove the new bridge or human/native QA.

## Still required

Connect these methods to the accepted-frame panel with explicit price readback,
guardian confirmation, saved-reservation recovery and progress/result presentation.
The methods are not yet called by the UI. Continue real image/video creation,
tail-frame continuity, QA/master generation and controlled release. No full SOP
is marked PASS; local synthetic receipts are not real production evidence.
