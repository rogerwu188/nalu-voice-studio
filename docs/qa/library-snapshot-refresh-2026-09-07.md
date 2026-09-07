# Same-run immutable library refresh

Status: IN_PROGRESS, core production handoff checkpoint; not product acceptance.

Inspection found that creating a second ordinary run would require resetting an
episode from PREPRODUCTION to SCRIPT_APPROVED. Instead, the dedicated refresh
keeps the run identity and episode status. No old package or workspace is changed.
The previous cross-run inheritance API remains available for explicitly prepared
snapshots, but native character confirmation should use this same-run operation.

`GET /v1/production-runs/{id}/library-snapshot-refresh` returns whether confirmed
library content differs and the exact version-bound request for the corresponding
POST. GET is advisory and read-only; POST rechecks all bindings transactionally.

POST holds the SQLite write transaction while validating current run, approved
script and shot plan, latest confirmed library, and absence of downstream work.
It writes a deterministic, fsynced package in a separate `library-snapshot-{hash}`
directory, materializes the actual Qingshan workspace and passes local preflight.
Only then do the package pointer and approved plan event commit together. Task
keys and creative/director content are retained; no remote tasks are copied or
created. Original package path, digest and plan event remain in provenance.

Preflight failure leaves original context current. The same request reuses the
same completed/staged package; corrupted or unsafe files fail closed. Successful
restart/concurrent replay returns the same event without repeating preflight.
Requests tied to old library/plan versions or started image/video work fail closed.
No payment, provider generation, script reset or additional key is involved.

Evidence:

- `tests/test_library_snapshot_refresh.py`: actual Qingshan materialization and
  preflight, original bytes/workspace retained, new library in sealed package,
  PREPRODUCTION unchanged, original run identity and zero remote tasks.
- `tests/test_shot_plan_inheritance.py`: synthetic preflight interruption/recovery,
  same deterministic path, replay without adapter calls, stale catalog and already
  prepared work rejection, concurrent requests returning one event.
- Related planning/library/refresh and progress-audit suite, including concurrent
  refresh: 46 tests passed in 16.75s.
- Ruff, OpenAPI export/backward compatibility and diff checks passed.

Still required: native confirmation callback integration and native UI QA, real
writer/source-to-script validation, live paid generation with explicit costs,
postproduction/master/controlled release, signed/notarized full E2E candidate.
Local Qingshan preflight is not real video-generation or end-to-end evidence.
