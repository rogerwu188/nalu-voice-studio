# Repair creative draft recovery — incomplete production flow

POST `/v1/production-runs/{run_id}/repair-shot-draft` accepts source run/event/plan
digest and target package digest. It checks explicit immutable repair lineage,
current source repair plan/seal, same episode/project/season, original approved
creative plan integrity, unchanged approved script and duration. It carries only
creative content into a new unapproved draft. New tasks await review and frames;
provider identities, spending and prior approval are not copied.

The transaction rejects existing target downstream work and provider tasks. Exact
restart replay returns the current identical draft; subsequent creative edits
prevent overwriting. Browser Origin calls are rejected. No model/network call.

Three repair integration cases pass4.28s; new assertions cover source hash mismatch,
Origin rejection, false approval/generation/spending flags, task reset, Runtime
restart replay and no overwrite after revision. Synthetic original plan fixture.
OpenAPI regenerated; native caller, real asset reuse and repaired master still
need implementation/QA. This is not a completed repair pipeline or SOP PASS.

Added read-only `/repair-shot-draft/context` for native clients to obtain exact
source event and immutable package hashes without reading local filesystem paths.
Runtime recreation/context identity and non-repair rejection added;3 cases pass4.28s.
Native transport now performs scoped context GET followed by draft POST and rejects
wrong parent, invalid digests or an approved/authorized response. Native transport
tests and UI recovery after partially completed preparation still need wiring;
do not mark the interactive journey complete. No automatic paid calls.

Native shot-plan loading now checks saved work first. Only if empty does it read
repair context and prepare the local original-plan draft; ordinary preflight
context returns null. A context failure leaves loaded=false, preventing paid
generation fallback. Existing saved drafts use only their normal GET and are not
overwritten. Added native tests for GET/GET/POST recovery, saved-draft GET-only
reload, failed context blocking generation and ordinary null context. Swift CI
and installed recovery QA remain pending. Backend3 repair cases still pass.

Recovery-context hardening: missing plan digest previously could raise a KeyError;
context now validates approval, digest and plan schema and returns409 for invalid
saved evidence. Regression includes missing digest and digest-consistent empty
shot inventory. All3 repair cases pass4.84s; ruff passes. This is rejection/error
handling, not evidence of real video repair or native recovery acceptance.

## Saved synthetic production fixture

Used isolated qv1poe20 SQLite (never user data) with its existing sealed parent
run_frame_review and child run_ddfaf60101144e24bf5b2f90b3961549. Context GET and
draft POST both returned200; saved evt_74d555b4e12c46ee9e514d80e5bb006f contains
the original two shots, approved=false and generation_performed=false. Exact
replay returned the identical event; original sealed-output integrity returned200.
No provider request or new video occurred. This exercises the saved full fixture
structure, not a real provider-produced film or native UI action.

Important QA state: qv1poe20 child now HAS a saved draft. Native reload there can
verify saved-draft display only, not the create-to-recover POST path. A fresh
isolated child is required to prove automatic native recovery end-to-end.

## Native automatic recovery on fresh child

CI34292299897 arm64 artifact (f4366e1), ZIP SHA256
`d878d23805d17faa1ccdf1877da55b4ed70962327ac51399fabfdb4aac426cf0`,
launched from `/tmp/nalu-repair-recovery-Zq59xd/extracted` using isolated
nel8waa9 support and port18767. Actual native confirmation created child
`run_dde421db8d4f41c783daaecbc9b77bff`. Opening its shot panel performed
GET current, GET repair context, POST repair draft (all200). UI displayed the
original sea shot and an explicitly unconfirmed recovered-draft notice; current
production remained30% preflight. No provider submission occurred.

Native restart, historical playback and actual media reuse remain unverified.
App remains active in exec session45725 for continuation. nel8waa9 now has a
child and must no longer be described as a parent-only fixture. Initial parent
opening-frame preparation returned409 at qa_review; this separate read-path
gap is not fixed by successful creative draft recovery. Full CI still pending.

Follow-up: CI34292299897 completed success. Native quit/relaunch on the same
isolated support loaded child through GET shot-plans/current200 only, with no
repair context or draft POST. Expanded panel displayed original sea shot and
unconfirmed state; SQLite retained exactly one drafted event and zero remote
task bindings. Restart session15134 was then quit. Actual repaired media and
full production/release acceptance remain open; no SOP promotion.
