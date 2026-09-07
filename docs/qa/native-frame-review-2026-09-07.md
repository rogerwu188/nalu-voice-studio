# Native first-frame review integration

Status: IN_PROGRESS. Source integration, pending compiled tests and native QA.

The existing confirmed-shot panel now contains an inline opening-image review.
It inherits scalable Nalu typography, system colors and large stacked controls:
“这张可以”, “这张需要修改”, and read-only reload. It introduces no new professional
form or implicit paid call. This is an Operate extension under the impeccable
skill, not a replacement identity or visual redesign.

The model selects only preparation matching the current plan/shot, then a saved
materialization matching the image task/request hash. Native preview checks the
returned bytes' SHA-256 before enabling review. Scope-specific view identity and
cancellation checks keep another shot's bytes out of this panel. Refresh clears
old actionable bytes; failed confirmation preserves the last known decision but
requires a reload. Provider credentials are never read by these operations.

Added serialized URLProtocol tests cover read/review, incorrect shot, changed
bytes and failed decision, with synthetic bytes labelled as such in test code.
Swift parser checks passed. Parser success does not establish type-checking,
compiled tests, installed UI behavior or image appearance.
Local `swift test --filter EpisodeFrameReviewTests` failed before tests at manifest
linking: missing `PackageDescription.Package.__allocating_init` on arm64. The
installed command-line toolchain cannot currently supply compilation evidence;
GitHub macOS CI is required before native inspection.

The skill's native screenshot/finish review remains outstanding until the CI-built
candidate can be inspected. No web detector was run: this is a native macOS view.
Pending QA includes empty/error/accepted/rejected states, actual image preview,
keyboard/large-font layout, switching projects/shots and restart. Native polling,
first-frame preparation/submission activation and video handoff also remain open.
