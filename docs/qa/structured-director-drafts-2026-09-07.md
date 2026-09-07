# Structured interactive director drafts

Status: IN_PROGRESS. Typed creative data and native source integration do not
establish a completed professional request, visual QA or real generation.

New AI plans must include per-shot director drafts: all ten protected camera
choices, explicit state-change/intentional-hold dimensions, prop endpoints,
visible-character counts, combat classification and prior-event relation.
Unknown prior events remain UNKNOWN. Continuing events require a proposed action;
hold shots require an unchanged state and reason. Counts cannot be booleans or
zero, dimensions/props cannot repeat, and extra QA/permission fields are rejected.
The selected design catalogue bounds all character/prop keys and prop owners.

Old plans decode with director=null. A native client round-trips the entire typed
draft rather than silently dropping it. Existing “听听这个镜头” includes a Chinese
readback and a disclosure shows the same text, using design names rather than IDs.
Impeccable's Operate/hardening guidance informed this existing-control extension;
no professional form or new voice engine is introduced. Compiled/native UI QA is
still pending; the Mac was last observed locked.

User changes to camera, action, framing descriptions, source, duration or visual
selection invalidate unchanged technical choices without losing the user's edit.
An unchanged edit from a client that drops director data is rejected. Such
invalidated drafts still need AI re-derivation before production; that endpoint
and full request compilation are unfinished and must not be replaced by invented
authority or copying stale parameters back in.

Targeted final backend tests: 21 passed in 13.96s. Tests include real runtime
draft/review/restart with synthetic model responses, invalid director data, missing
director and invented visible-person scope. Swift round-trip/readback tests were
added but await CI. OpenAPI is exported and backward compatible; Ruff passed.
Full regression collected before the last two negative cases: 607 passed in
296.41s. The final 21-test targeted run separately includes those missing-director
and invented-person cases. Swift compilation, native readback and current CI
remain pending. No real provider/paid call occurred.

Prior candidate `3f11ce3` completed all CI jobs in
[34074197880](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34074197880),
including the previous aspect-ratio fix; this is not evidence for the new draft code.

Next: durable, version-bound AI re-derivation after user edits; compile confirmed
drafts with actual registered assets and accepted-frame evidence into full camera,
state, identity and prop contracts. Keep real price/native spending activation and
sequential video/master/release acceptance open.
