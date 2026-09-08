# Synthetic native repair fixture

`scripts/create-native-postproduction-fixture.py` completed successfully with no
real provider execution. It uses the existing rendered static-frame test scenario
and resolves the macOS temporary directory before creating managed paths.

Support root:
`/private/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-postproduction-d7l59eeu`.
Database `nalu.sqlite3`; run `run_frame_review`, episode
`ep_8e662cd57d01444c842913f9b793acad`, both in qa_review with approved script1.
Saved events include confirmed edit, timed sound plan, reviewed recordings,
dialogue stage, four synthetic sound layers, rendered output seal and failed QA.

Repair plan SHA256:
`006af95fdd076a73327733401aef77b8b031dbc319b30add90b88f4f30a5f889`.
Sealed master SHA256:
`b6245d18902d05ef9e2bbadac75040666886c0faeb1a7c241b94a93947f9069d`.
Blocking codes: decoded_video and frame_repeat. This is intentionally not a
professional or accepted film. No repair child has been requested yet.

Use an artifact containing6387039 or later for native recovery/confirmation QA.
CI34279458243 (8c9e318) has started; no native repair acceptance claimed here.
