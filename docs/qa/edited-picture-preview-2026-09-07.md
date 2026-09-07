# Actual edited picture preview — IN_PROGRESS

Native-only POST `production-runs/{run_id}/episode-edit-drafts/{edit_id}/picture-preview`
now decodes adopted sources at the exact saved ranges and encodes a contiguous
24fps MP4, capped at 640px on the longer edge. It is a transient picture-only
preview: no authored sound, captions, approval, provider generation or release.
Response headers bind the edit hash and actual preview SHA256, declare no audio
and explicitly deny master acceptance. Responses are no-store/nosniff.

The service revalidates the latest exact edit, plan, current adopted media and
staged source hashes before and after rendering. Temporary output is private and
deleted on exit, rather than promoted to a master. Encoding is outside a database
writer lock, with cancellation/status checks, a five-minute deadline and 128MB
output cap. One preview per runtime process may render at a time. Rendering errors
are translated to a recoverable 409 without leaking filesystem details.

50 backend regressions passed in 13.68s. The two-shot test renders actual synthetic
media into a 13-second, 312-frame MP4, then fully decodes it and checks the final
frame timestamp, absence of audio, content SHA and master-denial headers. Wrong
edit hashes, browser Origins and corrupted staged files reject. An initial test
exposed an unhandled corrupt-source exception; the route now translates it and
the rerun passed. Ruff services/tests/scripts and diff check passed; OpenAPI updated.

Remaining: native file download/playback with exact-header and hash validation,
installed-player compatibility/visual QA, explicit edit and changed-duration
confirmation, real audio/caption alignment, full master QA and controlled release.
This is actual local proxy encoding on synthetic inputs, NOT real-provider E2E
or a final video. Parent 2459019 CI 34092812719 pending at this checkpoint;
503c6fb CI 34092538522 in progress. No SOP promoted to PASS.
