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

The current Runtime accepts an external writer declaration but does not contact
that provider and cannot verify the declared receipt. Such a record is always
returned as `external_unverified`, with `writer_receipt_verified: false` and
`network_call_performed_by_runtime: false`. A client cannot change those fields.
A later trusted writer adapter must reconcile a real provider receipt through a
separate versioned contract; it must not silently upgrade this declaration.

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
