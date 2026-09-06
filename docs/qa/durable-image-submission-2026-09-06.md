# Durable image submission observations

Status: IN_PROGRESS. Runtime service with mock-provider verification, not an
exposed paid workflow or successful real image generation.

`ImageSubmissionService` uses existing SQLite run events for image intent,
unconfirmed outcome and bound provider task receipt. An immediate transaction
serializes same-run/task submissions, checks the current eligible run, invokes
the mandatory trusted approval validator and commits intent before network I/O.
The exact endpoint plus request bytes are hashed. The image transport rechecks
that hash, current intent and authority immediately before POST. No credentials,
reference bytes or provider error bodies enter these event records.

An existing task/request returns the current saved observation; changed request
bytes conflict. Successful response replay returns the stored provider task ID.
Lost responses, revoked approval after intent and crashes before receipt commit
retain an uncertainty record and never resubmit automatically. Concurrent
observers may see that intermediate uncertainty; the winning request owns the
single POST. Receipt storage records acceptance only, with image_generated and
billing_verified false. The image ledger is distinct from video task bindings.

Records remain in the existing backup-preserved run-events channel. If imported
run identity or a record digest differs, submission fails closed pending
reconciliation; this is not a claim that image-specific import reconciliation
has already been implemented or separately QA-tested.

`tests/test_image_submission.py` covers accepted response/restart, HTTP failure,
authorization denial with no intent, concurrent calls, authority revocation
before HTTP, process-loss simulation after HTTP, changed-request rejection,
dry-run/cancelled/archived refusal. All provider I/O uses MockTransport and the
authority callback is explicitly synthetic; no real image or fee was requested.

The required authorization callback is trusted runtime code, not HTTP caller
data, and must do read-only local validation. There is no permissive default and
no public image submit route. Concrete image cost approval, upstream scope,
entry-state/spatial/image-model contracts and reference consent must still be
wired into this callback before native activation. Task query/media retrieval,
visual frame lock and complete real image→video→master→release QA remain open.
The service is infrastructure for that workflow, not a substitute for it.

Local verification: 451 tests passed (67.81 seconds); after adding the downstream
shot-edit lock, the affected image/shot suite passed all 19 tests and Ruff passed.
Shot review now refuses changes after an image intent, unconfirmed submission or
accepted task, as well as existing video preparation. Tests isolate each event
state independently. No native or real-provider image QA is claimed.
