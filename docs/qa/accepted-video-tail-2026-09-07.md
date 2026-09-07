# Accepted-video tail derivation — IN_PROGRESS

Added native-only extraction and PNG preview routes for the true decoded final
frame of an accepted shot. The receipt binds review, source video hash, exact
frame index/timestamp and extracted PNG digest. No image generation is performed.
The existing PyAV codec encodes PNG; no new runtime dependency is required.

Every extraction/read checks the latest accepted decision, immutable source media
and current validated preparation. Changed/rejected decisions invalidate old tails.
Writer locking and exact receipt replay deduplicate restart/concurrent extraction.
Only metadata is stored: PNG is reproducibly derived from the immutable local
video and checked against its receipt rather than storing duplicate media in SQLite.

32 regression tests passed in 11.47s. Tests compare extracted RGB pixels against
the final decoded source frame, verify exact frame index/time, restart/concurrency
reuse and stale-review rejection. The existing real-validator synthetic assembly
test now includes acceptance and tail derivation. Initial Pillow import failed;
it was removed in favor of the already packaged PyAV codec before passing tests.

Parent native playback 186f254 full CI 34087011213 succeeded. Review backend
f6e89d6 CI 34087400061 was in progress at check. Current CI required.

Still open: native adoption/rejection controls, wiring accepted tails into the
continuous-shot compiler/dispatcher, actual native playback QA, real provider video,
episode master QA and controlled release. This is not continuous-shot E2E completion.
