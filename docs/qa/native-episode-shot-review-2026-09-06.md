# Native episode shot-plan integration

Status: IN_PROGRESS, implementation checkpoint; packaged native QA pending.

Local related backend regression: 85 passed in 10.60s; Swift syntax and diff
checks passed. Earlier CI 34066540063 failed on the concurrent observer-order
assertion already corrected in b0f70db (its three macOS jobs passed). That is
not a current green candidate. CI 34066744041 was in progress at observation.

`ContentView` now places an episode-specific disclosure directly after production
progress. Its identity is the selected run ID, so switching runs creates an
independent view model. Opening it loads the saved current plan with a read-only
GET. It does not generate or invoke a model automatically.

The panel offers one-shot-at-a-time selection, literal script excerpt, local TTS
readback, editable natural-language video description, save and explicit version
confirmation. It inherits the existing `naluFont`, large native buttons and system
colors. Impeccable's Operate guidance was used for this narrow extension, not a
new visual identity. No HTML/CSS detector applies to this native SwiftUI view.

Generation uses the configured Hops model and existing Keychain credential,
through the runtime-owned shot endpoint, after an explicit model-cost dialog.
Failed or uncertain attempts are not automatically retried. Reading, saving and
confirming use no model key and invoke no model. Local unsaved edits disable
confirmation, survive failed saves, and require an explicit discard before reload.
Editing is disabled while a save is in flight. Creative approval is never called
paid approval, video generation or publication.

`EpisodeShotPlanTests` covers saved-plan decoding, dirty-state confirmation
blocking, failed-save retention, exact-version approval routing and no credential
headers in local review requests. An encoding test proves approvals do not
carry a replacement plan or payment authorization. Local `swiftc -parse` passes;
this is syntax evidence, not typechecking, compiled tests or UI QA. The existing
local Swift SDK mismatch means CI must compile and run these tests, followed by
isolated packaged-app verification. No success is claimed for those pending gates.

Remaining: successful CI; packaged screenshot and interaction evidence at actual
window size and large type; the Impeccable finish review after captures; free-form
spoken shot edits (current view offers a text edit and TTS readback); downstream
compilation of revised descriptions with action/sound/continuity fields; entry-
frame generation and concrete approved-plan binding; real video/master/release.
Neither model tests nor this panel completes the user's pure-voice workflow.
