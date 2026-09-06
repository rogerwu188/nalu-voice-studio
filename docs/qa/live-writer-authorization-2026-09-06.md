# Real configured writer request

Status: WAITING_AUTH for live provider generation; other SOP work can continue.

One explicitly enabled synthetic narration QA request used the existing Nalu
Keychain credential, configured `https://hopsapi.com/v1` destination and
`gpt-5.4-mini` research/writer model. The body uses the app's writer instructions,
Chat Completions JSON mode, `store: false` and the app's 8,000 completion-token
limit. No family material, video request, publication or credential changes.

Observed result: **HTTP 401**, not a missing locally saved key. This establishes
an authorization rejection from the configured endpoint, not its root cause;
the key's validity, scope and account access need checking with Hops. It does not
prove a model generated a script. No automatic retry occurred.

Local attempt evidence:
`/tmp/nalu-receipt-app.KpcDF6/live-writer-qa/writer-attempt.sqlite3`, state
`needs_review`, stable attempt `nalu-hops-narration-qa-v1`, request SHA-256
`62732249ec59b39b9eccf7242a438b782e8fa81f5d900d9fbad461b6859ccaff`.
The secret and rejected response body were not persisted or printed. The opt-in
script refuses to resubmit an existing attempt even if its prior result failed.
Its regression test verifies 401 redaction and exactly one transport call across
two invocations. Ordinary CI does not run the live command.

Reference checked: [OpenAI Chat Completions](https://developers.openai.com/api/reference/ruby/resources/chat/subresources/completions/methods/create).
OpenAI's schema does not establish Hops account authorization or compatibility.

Receipt-enabled native artifact `9997030619` from `7d9c490` was also downloaded,
checksum/deep-strict ad-hoc signature verified and launched on the existing
isolated port 18769. ZIP SHA-256:
`8f98f3cf82464f5bdf7a23a51ba8a725605cba168e228b39e4a586fbb9443c7c`.
It predates queued-supplement changes. Native receipt adoption is still pending;
startup alone is not acceptance.

Packaged runtime follow-up succeeded: created isolated synthetic project
`prj_5cbd6dab0cec4e7ca756d5f1ddc275ca`, stored two fixture-authored drafts,
created both script revisions and reconciled their distinct receipts over actual
HTTP on port 18769. Both returned `artifact_binding_verified: true`,
`provider_execution_verified: false`; neither script was approved. This verifies
the downloaded runtime adapter, not a live provider or the native adoption action.

CI [34059397691](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34059397691)
completed successfully on `7d9c490` for runtime, arm64, x86_64 and universal.
This does not include the later queued-supplement changes or prove live provider
access. Full product acceptance remains incomplete.
