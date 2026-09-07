# Exact local first-frame preview and user review

Status: IN_PROGRESS. Runtime APIs and fixture tests, not native or real-provider QA.

The image-result content endpoint returns verified PNG/JPEG bytes from a saved
materialization. It verifies run, observation, receipt/request and byte hashes;
it accepts no filesystem path, performs no download, rejects browser-origin
requests, and returns no-store/nosniff headers. Returning verified bytes instead of
a later file-path response avoids a changed-file gap between verification and send.

The review endpoint binds accept/reject to a materialization digest and the saved
image preparation. It rematerializes the current confirmed shot/reference request
locally before recording the decision. Accepted frames must match project aspect
ratio. Each changed decision requires the latest review event ID; the same current
decision can be replayed after restart. Old decisions cannot overwrite later ones.
Existing video preparation/reservation or provider binding blocks new decisions
pending downstream reconciliation.

User approval is explicitly separate from professional visual semantics, identity,
entry-state/spatial QA and paid authorization. Recording an accept decision does
not invent any of those PASS results or invoke generation. A rejected image is
preserved alongside its decision and can be reconsidered through a new version.

Tests use a synthetic approved script/shot and mocked image receipt, download and
provider observation with an actual fixture PNG. Targeted preview/review/download
suite: 19 passed, including accept/reject, restart, stale decision/digest, changed
file/plan and downstream preparation. Ruff and backward-compatible OpenAPI passed.
No actual user/native click or real generated frame is asserted by these tests.

Full local suite: 498 passed in 66.19 seconds. After final response-schema,
downstream-binding and shared saved-byte verification changes, the affected
19-test suite passed again; Ruff and progress structure audit passed.

Next: native preview/review integration, binding accepted image selection into the
video request path, complete professional/paid image contracts, continuous previous
final-frame handoff, actual image/video/master/release and same-candidate QA.
