# Persisted timed recording drafts — 2026-09-07

Added POST/GET `/v1/production-runs/{run}/audio-takes/{take}/transcripts`.
Drafts are SQLite run events bound to the exact accepted take/review and the
actual decoded PCM SHA/sample count. They preserve ordered relative word times,
confidence, recognizer version/time and text. Server validation rejects invalid
or out-of-window segments and mismatched audio. Browser-origin writes are blocked.

Saved output is explicitly `CLIENT_REPORTED_LOCAL_ASR_DRAFT`; audio hash matching
does not prove the recognizer was run or that its words are correct. Caption,
alignment and master approval flags remain false. Current media/consent/review
are revalidated on save, replay and recovery. Exact replay returns the original
event; GET does not create events. Rejecting the recording invalidates access to
its draft as a current subtitle candidate, without deleting its history.

Synthetic workflow tests cover empty recovery, origin rejection, wrong audio hash,
invalid intervals, successful save, same-event replay, restart recovery, unchanged
event count and rejected recording. Full workflow regression: 26 passed in 29.42s.
Ruff, OpenAPI contract and diff checks passed. No live ASR or paid calls were made.

Native persistence/recovery consumption and visible subtitle review are next.
Real ASR/cancellation QA, final captions, mix, master and release remain open.
No SOP status is upgraded. CI 34103363309 had Runtime/ARM passing and Intel still
running when checked; this checkpoint still needs its own CI result.
