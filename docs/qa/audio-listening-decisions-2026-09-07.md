# Exact recording listening decisions — IN_PROGRESS

Added native-only POST audio-takes/{take_id}/reviews. Accept/reject binds the
actual take SHA, source asset/hash/window, sound plan and current edit acceptance.
The current take is revalidated by the existing recovery/decode/consent path
inside the same SQLite writer transaction. Another candidate cannot be approved
using a stale listening action. Prior decision ID provides compare-and-swap;
exact current requests replay their event, while old contradictory decisions
are rejected. Existing master/materialization work blocks changed decisions.

The receipt states USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY. It approves only a
recording take: speech alignment, captions, final mix, master and generation
remain false. A successful decode or audition never automatically accepts sound.
Native listening controls and downstream accepted-take consumption are still open.

Validation: all 26 image-review/audio workflow cases passed in 21.85s. Synthetic
tone tests cover wrong hash, browser Origin rejection, accept, reopened replay,
stale reject, versioned reject and revoked consent denial. No real family speech
or actual listening QA is claimed. Scoped Ruff, diff and goal-progress audit
passed; OpenAPI regenerated. Parent corrected-progress CI 34099649847 is pending;
current full CI and installed native QA remain unverified.

Next: native explicit listened-to take confirmation and exact accepted-source
handoff into speech-based caption alignment, authored audio and master/release.
