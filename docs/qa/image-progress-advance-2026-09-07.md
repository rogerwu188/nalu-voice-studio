# Accepted image task → review-ready progress

Status: IN_PROGRESS; backend integration evidence, not paid or native acceptance.

`POST /v1/production-runs/{run_id}/image-tasks/{submission_id}/advance` now joins
saved accepted-task validation, one read-only provider status query, durable
observation, bounded image download and verified local materialization. It
returns `waiting`, `provider_failed` or `ready_for_review` with local evidence IDs.
It has no generation POST callsite. Image submission approval remains separate.

Terminal observations survive restart: completed results resume interrupted
download without querying again; failed/error results remain failed without a
replacement task. Existing local images are revalidated rather than downloaded
again. Missing/changed files require reconciliation. Pending work takes one query
per explicit advance, never an unbounded loop. Unexpected multiple outputs for
the single-frame request require reconciliation rather than arbitrary selection.
Cancelled runs cannot advance, including cancellation during query/download.
Archived projects and unconfirmed/tampered task receipts remain fail-closed.

The native credential header is transient and browser-origin calls are rejected.
Responses contain no provider URLs, private paths or credentials. Download uses
the existing pinned-public-host, bounded PNG/JPEG downloader, not a key-bearing
provider client. This endpoint never claims visual QA, billing verification,
user frame approval or a completed master.

Validation: 15 targeted tests passed (3.46s), using synthetic task receipts,
mock HTTP, synthetic images and explicitly fake test authority. Ruff passed and
OpenAPI changes were backward compatible with the previous HEAD. The full local
suite was running at this checkpoint's initial evidence write; its result must
be recorded before calling the regression check passed.

Still open: native orchestration calls to this endpoint; exact cost authority
and full QingShan image contracts before any real image submission; real output
and user review; video production, postproduction and controlled release. The
Mac lock prevents native interaction QA, not these remaining implementation steps.

Full local regression completed: **513 passed in 68.49s**. That collection
preceded the final cancellation-during-download test addition; the final
15-case targeted run includes that additional case and passed. No live HTTP
generation or user-data mutation was involved in either test run.
