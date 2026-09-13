# Native final-review handoff inspection

Inspected source candidate `e533a87a8f887008130a090183540cee136aa35e`.
Scope: source inspection only, not installed QA or human acceptance.

## Confirmed wiring

Attestation contract hardening: `FinalQAEvidence` now uses strict validation.
Strings such as `"true"`/`"yes"` and integer `1` can no longer be coerced into
human approval. Thirty negative field/value cases and a valid JSON round trip
pass (31 tests); existing missing/failed final-QA repair tests pass (2 tests).
This protects ingestion but does not implement the missing endpoint or UI.

- `VoiceInterviewViewModel.verifyFinalMaster` downloads the sealed master,
  invokes on-device Apple Speech, and submits semantic QA. Its success message
  explicitly requires subsequent original-resolution human review.
- `ProductionVersionHistoryView` downloads and plays an identified sealed
  version, but playback intentionally does not create acceptance evidence.
- The backend `FinalQAEvidence` requires the exact run/master digest, reviewer,
  original-resolution review and all six release checks.

## Missing handoff

Backend inspection adds an important constraint: `ProductionEngine.complete_run`
does not ingest a review. It reads exactly one `qa_report` artifact already in
the immutable output seal, then validates `FinalQAEvidence` and run/master
bindings. `app.py` exposes semantic QA, but no final human-evidence ingestion
endpoint. Thus adding a Swift submission method alone cannot close this gap.
The implementation must resolve review-before-seal versus post-seal review
without rewriting an existing seal or weakening completion's binding checks.

The native sources contain no `FinalQAEvidence` submission model or action.
Playback and semantic QA therefore do not provide a native route for recording
the required explicit final human decision. This is a product implementation
gap, not proof that all remaining work requires provider authorization.

Next: inspect the backend final-evidence ingestion and persistence boundary,
then add a digest-bound native transport and recovery contract before wiring
explicit review controls. Preserve negative decisions; never manufacture human
attestations from playback, download or semantic QA success. Existing sealed
synthetic outputs may test transport only and must not be rerendered or used as
real content acceptance. No SOP status is promoted by this inspection.
