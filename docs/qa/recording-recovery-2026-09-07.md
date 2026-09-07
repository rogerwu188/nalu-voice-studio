# Recording attachment recovery — IN_PROGRESS

GET audio-takes takes the exact sound-plan ID/hash and returns the latest attached
candidate per cue in cue order. Saved take digests, current approved edit/preview,
source recording bytes, decode coverage and live consent are revalidated. No
replacement event or asset binding is created by recovery. Invalid/revoked
sources fail explicitly rather than being silently restored or dropped.

An initial regression exposed integer default `0` versus parsed float `0.0`
source-offset hashing. New requests normalize the default to float. Recovery
checks historical receipt integrity first, then compares typed content without
rewriting its original hash. Explicit zero and omitted zero now replay the same
event. Native consumption of this recovery endpoint remains to be implemented.

Validation: 26 workflow tests passed (30.38s), followed by the targeted synthetic
audio workflow with the extra zero-offset replay assertion (1 test, 8.59s).
Tests include reopened Runtime GET, unchanged event count, wrong sound SHA and
revoked consent denial. Scoped Ruff/diff passed; OpenAPI regenerated. Parent
7b8a0be full CI [34097684986](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34097684986)
passed. Current code still requires CI, and installed source-audition/native QA,
real narration, alignment, final sound and master/release remain unfinished.

Next: consume recovery in native recording selection and reconcile uncertain
attachments, then user take confirmation and actual subtitle/audio production.

## Native read-only recovery checkpoint

RuntimeClient now requests audio-takes with URL-encoded sound-plan ID/hash and
validates every returned cue, review, source digest, sample count and QA flag. It
rejects duplicate cues rather than silently overwriting. EpisodeAudioModel loads
these bindings alongside scoped assets and checks each recovered asset/hash is
still in the usable inventory before making the result actionable.

An uncertain attach is resolved by GET only when the saved cue/asset/hash/source
offset matches exactly. Unmatched requests remain pending, and a failed read
keeps source data but disables new selection. Native tests added for GET-only
restart recovery, query binding, uncertain result reconciliation and duplicate
cue rejection. Current native CI remains required. Backend recovery regression
passed again (1 test, 10.03s), scoped Ruff/diff passed. Native UI parent 1751f3e
CI 34098405655 was still in progress at inspection.

The model recovers bound records; restoring the visible picker/offset and
auditioning exactly that recovered source segment still needs wiring. Final
listened-to decisions, speech alignment, authored audio and master/release QA
remain incomplete. Installed app has not been updated or visually verified.
