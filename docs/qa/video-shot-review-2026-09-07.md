# Version-bound video decisions — IN_PROGRESS

Added native-only video review endpoint. Decisions bind exact materialization,
video hash, provider binding and current validated preparation. Acceptance checks
duration and aspect ratio; changed inputs or media cannot inherit approval.
Optimistic review IDs prevent stale edits; identical replay/concurrent requests
return one receipt. Existing postproduction/master work blocks changing decisions.
User acceptance never asserts visual/audio QA, billing or master acceptance.

41 tests passed in 11.65s across video review, image review, materialization and
progress audit. Seven decision cases isolate preparation validation. The existing
video-assembly integration case additionally runs the actual plan/frame/video
validators through synthetic video materialization and acceptance. No real
provider generation, charge or human visual QA occurred.

Native adoption/rejection controls, accepted tail-frame extraction/continuation,
episode assembly, installed-app QA and real end-to-end release remain open.
No SOP changes to PASS.
