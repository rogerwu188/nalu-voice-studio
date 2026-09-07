# Accepted recording transcription bridge — 2026-09-07

Added a local recording transcriber that reuses the existing on-device Chinese
Apple Speech recognizer. It takes validated accepted PCM bytes, checks their SHA
and bounded sample size, writes a private temporary input (directory 0700, file
0600) and removes it on recognizer success/failure. It never switches to cloud
recognition. The result retains take/review/audio identity and local recognition
version/time, with timestamps relative to the exported recording window.

Draft validation rejects empty transcripts, invalid timestamps, overlapping or
out-of-window segments, nonfinite confidence and oversized result inventories.
Both subtitle approval and speech-alignment verification remain false. Recognition
timestamps are candidate captions, not a forced-alignment or master QA result.

The recording review model can now orchestrate approval recheck → exact PCM
download → local recognition → approval/consent recheck → draft retention. New
recording decisions invalidate the draft. It cannot start from an unapproved or
unresolved recording decision. The visible trigger, draft persistence/review and
downstream caption/master assembly are not yet wired.

Native test source uses an injected recognizer and synthetic PCM to check exact
input, private permissions, cleanup after success/failure, source identity and
invalid intervals/confidence. A model test checks no recognition/download work
for historical-only approval. Native execution awaits CI; this is not live Apple
ASR/permission or actual family QA. Existing recognizer timeout/cancellation also
needs verification before claiming production readiness.

Backend export regression: 1 passed, 25 deselected in 25.34s. Ruff/diff passed.
CI 34102388611 for e68923c12fb5ab4a8debdc4da95938ab58a11617 is fully successful.
Current native code still requires its own CI and installed QA. No SOP upgraded.
