# Exact preview-bound edit decisions — IN_PROGRESS

Picture rendering now journals the actual output SHA, byte/frame counts, duration,
geometry and edit hash after final source revalidation, and returns its receipt
ID in `X-Nalu-Preview-Receipt-ID`. Rendering does not assert the user watched it.
Identical receipt replay deduplicates; temporary proxy bytes are still transient.

Native-only edit-review POST accepts an exact edit hash, rendered preview receipt
and output SHA, explicit accept/reject decision, reviewer and confirmation text.
It verifies current source media and edit state under a writer lock, validates
the preview receipt, and uses expected-review-ID compare-and-swap. Same current
request replay returns its prior record; stale decisions cannot override newer
ones. Downstream postproduction/master events prevent new decision changes.

The immutable review records both planned and edited duration, the preview
identity and explicit user attestation. This is not playback telemetry or human
QA evidence by itself. Accepting the picture edit does not approve audio,
captions, billing, master or release, and does not alter the original episode plan.

The two-shot actual-encoding fixture passed in 4.95s: proxy receipt is not viewing
proof; mismatched SHA/Origin reject; rejection replays after restart; accepting
requires the current decision ID; a 13-second edit remains distinct from the
15-second plan; old rejection cannot replay after acceptance; corrupted staged
media invalidates even a previously accepted request. Ruff passed, OpenAPI updated.
Full image-review/video-materialization/video-download regressions subsequently
passed: 50 tests in 15.55s. Parent bbdc648 CI 34093687404 is pending and 83a3def CI
34093298594 is in progress; neither is claimed as this checkpoint's acceptance.

Still required: native receipt preservation and explicit readback/confirmation,
current CI, installed-player and user-flow QA, downstream use of exact approved
edit, real audio/caption alignment, full master QA and controlled release. No SOP
is complete from this backend review contract or synthetic user attestation.
