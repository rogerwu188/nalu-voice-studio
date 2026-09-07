# Confirmed native shot → automatic local frame preparation

Status: IN_PROGRESS — native wiring implemented; compiled/native QA pending.

The native frame-review model no longer stops at an empty "not prepared" state.
For the selected confirmed shot it calls the runtime's new
`POST /v1/production-runs/{run_id}/shot-plans/{plan_id}/opening-frame-preparations`
with only the selected `shot_index`. The runtime resolves episode task identity
and exact current plan hash, then uses the existing validated image preparation.
Users never enter task keys, hashes, image parameters or professional contracts.

Preparation is local and idempotent, not an image-provider invocation. The
endpoint accepts no credential or spending permission. Existing preparations are
reused; stale plans, invalid indexes, cancellation and browser-origin requests
are rejected. Current script, asset, permission and resolution checks remain in
the existing preparation service. Continuous shots still require the previous
reviewed final frame; this entry does not bypass that missing handoff.

The client checks response run/plan/shot identity before adoption. It retains
the busy guard and cancellation checks, shows preparation versus actual image
availability separately, and leaves frames unconfirmable until verified image
bytes exist. Failure does not recreate the story project or request an API key.
The message limits "no new generation/charge" to this preparation/read action;
it does not assert that earlier provider work was free.

Impeccable hardening guidance was applied narrowly to empty/error states and
repeat actions, preserving the existing native visual design. No visual polish
or unrelated redesign was introduced. Screenshot/keyboard/large-font QA is still
pending because native interaction was blocked by the locked Mac.

Validation: 22 targeted Python tests passed in 3.64s. Swift URLProtocol tests were
added for automatic preparation and failure with no provider credential, and
existing wrong-shot expectations were updated. Local `swiftc -frontend -parse`
failed before useful validation with duplicate `SwiftBridging` module definitions
in CommandLineTools; this is **not** a passing compile or test result. Await the
new commit's macOS CI rather than altering system developer tools. Ruff passed;
OpenAPI export/compatibility and full regression run are recorded separately.

Still open: real upstream image contract compilation and reference production,
authoritative image price, native spending confirmation/submission/progress
orchestration, actual frame/video/master/release acceptance. Automatic local
preparation does not make the full production pipeline complete.

Full Python regression subsequently reported **539 passed in 73.54s**. The
OpenAPI contract is current and backward compatible with the preceding HEAD.
These results do not include compiled Swift tests or real native interaction.
