# Reviewed opening-image preparation

Status: IN_PROGRESS; local runtime/API implementation, not actual image output.

`POST /v1/production-runs/{run_id}/image-task-preparations` takes only the saved
plan event, plan digest and task key. Nalu compiles the confirmed image description,
entry state, scene, camera and project aspect ratio into a concrete pinned Giggle
image request. Users need not retype professional prompts. This endpoint performs
no provider I/O, needs no key and grants no spending authorization.

Current run/package, approved script and episode duration are rechecked. References
come from episode-inherited, unchanged managed assets, never caller-supplied paths
or URLs. Character references require the saved consent record and applicable
guardian permission. Linked memory cards must be confirmed for visual generation;
documentary references require that linkage. Only bounded, decoded PNG/JPEG images
are accepted, with at most nine references and the transport's aggregate limit.
No references are silently omitted. Audio/video/document bytes require an explicit
reviewed still-image preparation before this image-only path can consume them.

Continuous shots are explicitly refused here until their reviewed preceding final
frame exists; they must not independently regenerate an unrelated opening image.
That final-frame handoff is still pending, not fulfilled by this refusal.

Preparation persists prompt, exact endpoint-bound request digest, source version
and reference hashes/dimensions. It does not copy image bytes, local paths or
consent statements into its event. Repeating preparation after restart returns the
same saved record. Actual submission must rematerialize and verify these bindings,
add concrete cost/production-contract authority and then use the durable submitter.
The public preparation endpoint deliberately does not activate paid submission.

Tests use synthetic scripts/plans, an actual managed PNG and isolated SQLite. They
cover no-reference/reference preparation, repeat after restart, stale/unconfirmed
plans, unknown shots, changed script/ratio/bytes, cancellation, revoked consent,
invalid image and memory confirmation/use restrictions. No real AI, image provider,
charge, native UI action or completed video is asserted by these tests.

Local results: full suite 466 passed in 67.41 seconds. Following style/reference-order
and stored-record integrity additions, all 15 affected preparation tests passed
again; repository Ruff passed. Exported OpenAPI is backward compatible with the
preceding commit. Native/paid end-to-end verification is still outstanding.

Remaining: paid cost/scope and complete QingShan image contracts, native orchestration,
image task query/download, visual first-frame review, continuous final-frame handoff,
video generation, master QA and controlled release on the same candidate.
