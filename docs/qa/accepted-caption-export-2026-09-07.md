# Adopted caption export checkpoint

Native-local GET exports a currently confirmed recording transcript as UTF-8
WebVTT. Timings include the recording cue's episode start offset. User text is
escaped as literal text and newline-separated cue injection is prevented.
Sub-millisecond intervals that collapse in VTT are rejected, not stretched.
Export revalidates the current caption review, transcript and adopted source
under the same transaction. Headers carry digest and exact identities, no-store
and explicit non-master status. Superseded confirmation cannot be exported.

Tests: caption unit cases plus synthetic media workflow: 6 passed, 25 deselected
in 22.43s. Includes absolute offset, escaping, timing bounds, deterministic GET,
digest, stale confirmation and stale transcript rejection; GET does not add
events. Ruff passed after import formatting; OpenAPI updated.

This exports one recording's captions, not a complete episode subtitle track.
Remaining: combine all current cue exports, stage dialogue PCM and required
audio layers with provenance, connect existing postproduction materializer,
final QA and controlled release. Native UI CI 34106778965 was still running;
no installed user QA or full release-candidate PASS is claimed.
