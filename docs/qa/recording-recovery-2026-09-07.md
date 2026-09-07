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
