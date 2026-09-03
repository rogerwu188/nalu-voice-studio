# Script authoring provenance

Every newly created script revision carries a server-sealed
`nalu.script-authoring-provenance/v1` record. This record describes how the
revision reached Nalu; it does not approve the story and does not authorize a
production run.

## Origins

- `user_dictation`: the user dictated the script or correction. The native app
  selects this when a non-empty source transcript accompanies the revision.
- `user_text`: the user entered the revision as text. The native app selects
  this for the visual editor.
- `external_ai_generated`: an external writer produced the draft.
- `external_ai_assisted`: an external writer assisted with the draft.

External AI origins require a bounded declaration containing the provider,
exact model ID, task/session ID, input-bundle and writer-rules SHA-256 digests,
receipt SHA-256 digest, and timezone-aware start and completion times. Generic
aliases such as `auto`, `default`, `claude`, `opus` and `fable` are rejected.
Nalu stores no prompt, credential or raw provider receipt in this declaration.

## Verification boundary

The Runtime accepts an external writer declaration but does not contact that
provider. Such a provenance record always remains `external_unverified`, with
`writer_receipt_verified: false` and `network_call_performed_by_runtime: false`.
A client cannot change those fields.

An operator can later submit the exact immutable Qingshan Writer v2 receipt as
raw bytes to the separate reconciliation endpoint. Nalu independently verifies
the receipt byte digest, canonical schema and completed state, allow-listed
Writer agent, exact provider/model/task identity, input-bundle and writer-rules
digests, authority-output digest and timezone-aware task interval. Duplicate
JSON keys, unknown agents, altered bytes and mismatched content fail closed. The
raw receipt, upstream paths, prompts and credentials are not persisted.

Successful reconciliation produces a server-sealed
`nalu.writer-receipt-reconciliation/v1` record. It means only
`artifact_binding_verified: true`: the supplied artifact is internally
consistent and is bound to this exact script provenance. Qingshan's current
receipt has no cryptographic provider signature, so the record must continue to
say `provider_execution_verified: false` and
`network_call_performed_by_runtime: false`. It cannot honestly prove that a
provider ran. Client assertions may not add that evidence.

Provider execution is a separate, optional verification step. Its endpoint is
disabled by default and requires both an idempotency key and the exact spoken or
typed confirmation “我确认只读核验 Writer 任务” (or its documented English
equivalent). An injected verifier must perform only an authenticated, read-only
provider-task lookup; it is forbidden to submit generation, spend credits or
modify the remote task. Nalu first persists a `submitting` transaction, then
compares the remote provider, exact model, task ID, completion state, receipt
digest and timestamps with the artifact-bound local record.

An exact match produces a separately sealed
`nalu.writer-provider-reconciliation/v1` record. Only this record may state
`provider_execution_verified: true`; it also states explicitly that the Runtime
performed no generation, paid generation or external write. Nalu stores a
digest of the bounded lookup evidence rather than credentials or the raw remote
response. A timeout, verifier error, malformed response or any mismatch changes
the transaction to `ambiguous`, blocks production for that script and forbids
automatic retry. The operator must investigate rather than risk a duplicate or
misattributed provider operation. Deterministic test verifiers prove this local
contract only; they are not evidence of a real provider execution.

For user-authored revisions, `user_attested` means only that the local request
declared a user origin. Narrative authority still requires the existing,
revision-specific user approval record (and guardian gate for a child project).
Neither provenance status can replace approval.

## Integrity and compatibility

The Runtime binds each record to the exact UTF-8 script content and source
transcript and seals its canonical body with `provenance_sha256`. The sealed
record is stored under the reserved `_nalu_script_authoring_provenance` key in
the existing SQLite `narrative_metadata_json` column. Public responses expose it
as `authoring_provenance` and omit the reserved key from narrative metadata.

Reads and project imports recompute all three digests and fail closed on altered
content, transcript, fields or seal. Existing databases and older project
exports without a sealed record remain readable, but Nalu labels those revisions
`legacy_unknown` / `legacy_unverified`; it never invents an author or model.

Both reconciliation layers live in dedicated SQLite migrations, are unique per
script revision and are covered by their own record seals. Project export v22
preserves and revalidates them while v1-v21 imports remain supported without
inventing either kind of evidence. When present, both records are copied into
the immutable episode production package so downstream compilation can
distinguish an artifact-bound Writer output, an independently verified provider
task and an unverified declaration.
