# Saved production task observation

Status: IN_PROGRESS; synthetic integration coverage, not real video acceptance.

The runtime now exposes `POST /v1/production-runs/{run_id}/tasks/{binding_id}/refresh`.
It resolves an existing Giggle task from the local binding, rejects cross-run
bindings and archived projects, and uses a transient provider-key header. Browser
Origin requests and missing keys are rejected. No task ID or destination URL is
accepted from the caller.

Responses become durable `provider_task_observed` run events, with response and
observation digests. Consecutive identical observations deduplicate. Restarting
the runtime preserves them. They do not change task identity, charge state, run
state, or approval. Completed observations show “waiting for retrieval and QA”
at 60%; failed/error observations retain the task and require review, not retry.

Validation:

- 71 tests passed across paid-submitter boundaries, Giggle query and SD2 image
  transport. Five status variants exercise the actual FastAPI endpoint,
  cross-run rejection, repeat queries, SQLite restart, unchanged billing state
  and episode progress.
- Previous checkpoint `ef7f78021433dce6bad60d1b7ffa17ff3e8c9172` full runtime
  regression: 373 passed. This is not the full suite result for this change.
- Ruff passed before final documentation update.
- Current change still needs pushed CI and native integration QA.

No live provider request, charge, download or publication occurred. Native query
dispatch, approved frame/price-to-submit wiring, bounded result retrieval, media
QA and real provider reconciliation remain open. Result URLs are candidates,
not trusted downloadable media or completed masters. SOP-04/08 are not PASS.
