# Actual accepted recording audio — 2026-09-07

GET `/v1/production-runs/{run}/audio-takes/{take}/accepted-audio` now provides
actual decoded WAV bytes for the exact accepted recording source window. The
caller must provide the take digest and current accepted review ID. Current
take/edit/media/consent checks execute under the same SQLite writer lock.

The export is 48 kHz stereo, 16-bit little-endian PCM. It uses the saved source
offset and exact decoded sample count, never silent padding, voice cloning or
provider generation. Decode duration/output are bounded (30-second processing
deadline, at most 300 seconds of audio); the original recording hash is checked
again after decode. Response headers bind the output SHA-256 and review/take IDs;
`Cache-Control: no-store` prevents stale approval-based caching. No events or
production-state changes are written by reads, including repeated reads.

Synthetic tests verify WAV format, exact sample count, non-silent actual tone,
output hash, deterministic replay without new events, rejection/wrong-review/
replacement/revocation blocking, and different waveform bytes after an explicitly
accepted source-offset change. `pytest tests/test_image_review.py -q`: 26 passed
in 31.56s. Ruff, OpenAPI contract and diff checks passed.

This is a real media transformation tested on synthetic audio, not real-family
listening QA. Native download/audition integration, speech alignment, authored
five-layer sound, subtitles, final master and release remain incomplete. It does
not claim a final mix or full episode completion. No SOP status changed.

CI 34101343116 for 5d10fe5425c93afa84bc15ab80055b194979a9ae now fully passed
(Runtime, ARM, Intel, Universal). Newer UI/recovery code and this checkpoint still
require their own CI and installed QA.
