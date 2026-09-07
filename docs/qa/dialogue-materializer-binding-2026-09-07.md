# Adopted dialogue materializer binding

Postproduction requests can now name the exact staged-dialogue receipt and its
digest. Adopted-dialogue source paths without that receipt are rejected. The
production service validates before rendering and again before recording a
successful materialization. Validation replays current staging checks and binds
the dialogue path/hash/offset/cue hashes, subtitle path/hash/review contract,
and exact adopted edit shots/frame rate. Other audio layers remain required;
this checkpoint does not synthesize or silently omit them.

Tests: 14 passed (0.86s), covering source-binding validator with a mocked staging
boundary plus existing synthetic dialogue/export tests. Mutations in subtitle
digest/contract, edit inventory/frame rate, staging digest and audio offset fail.
These tests do NOT demonstrate complete rendering or live consent change during
a render. Ruff/diff passed; OpenAPI exported. Current CI remains unconfirmed.

Remaining: construct the request from staged inputs and explicit sound-layer
choices, test full materialization with actual fixtures and cancellation/source
changes, wire native action/progress, then final QA and controlled release.

Request-preparation follow-up: a native-only prepare-mix endpoint now constructs
the full materialization request from exact staging/shot/caption receipts plus
four explicitly selected remaining sound-layer sources. Callers need not fill
the dialogue paths, offsets, cue hashes, caption contract or shot inventory.
Selected local files must exist and match hashes. No rendering or remote call
is triggered by preparation. Output is an executable request, not a render result.

Tests: 15 passed in 0.82s; request-construction test uses mocked staging validation
and file-identity fixtures, not real decoded sound layers. It verifies automatic
bindings and refusal of a changed selected sound file. Ruff passed after import
formatting; OpenAPI updated. Full managed-fixture prepare/render, native sound
selection, final QA and release remain incomplete. CI 34108693072 was running.
