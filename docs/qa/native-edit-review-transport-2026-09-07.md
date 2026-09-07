# Native preview identity and edit-review transport — IN_PROGRESS

Native preview download now preserves the server's rendered receipt ID, exact
content SHA and edit SHA alongside the private playback URL. Missing/unsafe receipt
IDs reject before playback. Lifecycle cleanup clears both the local file and its
review identity, rather than leaving a stale receipt available after changing cuts.

Typed native review transport binds requests to that picture receipt and the saved
edit, posts explicit accept/reject data, and validates the returned decision,
duration, actor, confirmation, preview and edit identity. It rejects fabricated
audio/caption/master approvals or generation claims. Read-only event recovery
loads the latest decision for the matching edit; unrelated event payloads do not
need to conform to the review schema. No provider keys or automatic approval.

Native test additions cover required preview-receipt headers, exact decision
request fields, GET recovery, no provider header and foreign-preview response
rejection. These tests await current macOS CI; local Swift manifest linker remains
unavailable. The actual backend encode/decision fixture passed again in 7.71s.
Ruff services/tests/scripts and diff check passed. Parent 037c846 CI 34094090038
is running, not stopped; bbdc648's queued CI was cancelled by newer work.

Still required: native explicit readback/accept/reject controls and uncertain-submit
retry state, installed playback/confirmation QA, exact approved-edit downstream
handoff, authored audio/subtitles, full master QA and release. Transport tests and
synthetic attestation are not evidence that a real user approved a real episode.
