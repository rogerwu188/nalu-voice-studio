# Native episode sound selection state

Status: IN_PROGRESS; no SOP promotion.

The selection model filters current episode/project assets, retains user choices
on refresh, and freezes an uncertain preparation request for exact retry. A new
choice, including changed offset/gain on the same asset, invalidates its prior
ready receipt. Cancelling that retry cannot silently restore old mix settings.
All four sound roles require validated receipts before exposing mix sources.

Added injected native test coverage for timeout, frozen retry, refresh, changed
parameters, abandoned retry and missing assets. These tests have not yet run:
local Swift tooling has the previously recorded duplicate SwiftBridging issue;
new commit CI is required. Backend source and dialogue-binding regression tests:
`22 passed in 0.51s`. This does not validate the new Swift code.

Prior transport commit 1787c600c45387c91ead76b137d57997769e7834 CI run
https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34253996299 was still
in progress when checked. No installed QA, paid request or final master occurred.

Native selection controls are now connected after adopted episode editing, beside
the existing recording panel. They expose role-labelled asset menus, preparation,
exact retry, unavailable-selection text, refresh and status readback. Large native
controls and wrapping copy preserve the incumbent accessible Operate surface.
Task cancellation suppresses late readback when the panel disappears. No server
rollback is claimed. Controls are not yet installed or visually verified; source
inspection and `git diff --check` are not substitutes for native QA.

Still required: connect prepared choices to prepare-mix /
render, recover choices across app restart, prepare missing sounds with authorized
real sources, and installed full episode / master / controlled release acceptance.
