# Authorized sound assets into actual episode mixing

Parent: `f36e91ca7bce40800b8c7795f5e64570f26bc3e0`.

Added native-only `POST /v1/production-runs/{run_id}/sound-sources` to prepare an
existing project audio asset as ambience, foley, music or SFX. Input is an asset
selection and sound-plan binding; output includes the generated managed path,
hash and cue bindings needed by mixing. No provider call or audio generation
occurs. This is not yet automatic sound design or a completed native selector.

Preparation validates the exact approved edit/sound plan, current scoped consent
and guardian authorization where needed, managed nonsymlink file identity and
actual decoded coverage of the whole episode window. It never pads or stretches
a short recording. Immutable local copy and SQLite receipt are replay checked.
An existing damaged/missing staged file is not silently overwritten.

The mixing constructor requires the same sound plan. Materialization validates
source authorization before and after rendering, and rendered-output integrity
rechecks it for sealing/master/release consumers. Changed or revoked original
consent fails closed. This is not atomic external publication proof.

The full existing two-shot rendering fixture now imports four explicitly
synthetic authorized sound assets, prepares each through HTTP, verifies short
source refusal, native-origin enforcement, exact replay and copied bytes, then
uses those returned sources in real encoding. It reaches QA_REVIEW and retains
the prior render/replay/dialogue-revocation checks. Sound authorization is also
checked positively then refused after revocation.

Evidence: actual synthetic full render test 1 passed in 70.34s; focused sound
source, dialogue binding, rendered consent and immutability regressions 58 passed
in 21.67s. OpenAPI regenerated. These tones are test fixtures, NOT professional
music/foley or a real user's completed episode. Current CI/native QA pending.

Remaining: native asset choices and role confirmation, automated preparation of
missing sound assets with authorized providers, native mix/render action,
subjective/semantic/master QA, installation and controlled release. No SOP PASS.
