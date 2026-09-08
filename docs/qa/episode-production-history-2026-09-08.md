# Retained production version discovery

Added GET `/v1/episodes/{episode_id}/production-runs`, newest first using the
same timestamp/ID ordering as active-run lookup. Missing episodes return 404;
episodes without runs return an empty list. Reading history never activates an
older run, changes episode state or starts production.

Repair tests now read history after Runtime recreation and verify both child
preflight and parent qa_review remain accessible, another episode returns no
versions, active-run selection remains the child and original files are unchanged.
All three repair cases pass (4.13 seconds); ruff passes and OpenAPI was regenerated.
Synthetic fixture only, not actual repaired video or native history UI acceptance.

Next: connect native version selection as read-only inspection, keeping production
commands bound to the current version; separately implement validated reuse of
eligible prior assets. Do not relax the existing library-only shot-plan inheritance
guard to copy provider tasks or stale approvals across production runs.

Native RuntimeClient now exposes GET-only version reading with project/season/episode
identity and duplicate-ID rejection. Added URLProtocol tests for preserved order,
cross-episode rejection and duplicate rejection, verifying all requests are GET.
Local Swift SDK remains mismatched; these new tests await macOS CI and are not
reported passed. Native selection UI is still outstanding.

CI34284802594 on e8c8a3e has since completed successfully. Together with the
separate native sound-read evidence this closes that narrow regression only;
it does not cover these newer version-history changes.

## Native inspection panel — awaiting build and QA

ContentView now places a collapsed version-history panel beside current production.
It explicitly reads the scoped version list, labels current/prior and dry-run
records, downloads only the selected sealed master using the existing digest
validation, and exposes VideoPlayer without production/approval/publication actions.
Large controls, existing naluFont scaling and a read-aloud status action preserve
the incumbent interaction style (impeccable local-extension guidance).
Selection/exit releases the player and deletes only its downloaded temporary copy;
an in-flight response after disappearance is discarded and its copy removed.

`git diff --check` passes. No local Swift build due to the recorded SDK mismatch.
CI build, actual parent-video viewing after repair, switching/exit cleanup and
native visual/finish review remain required. This is implementation, not UI PASS.

## Original master retrieval after revision

Extended repair regression reads the original sealed-master endpoint after child
creation and Runtime recreation, verifies exact returned bytes and digest header,
rejects unsealed child access, and confirms reading does not rebind the active run.
Tampering with the original fixture file then correctly returns409. All3 repair
cases pass4.20s; ruff passes. The deliberately invalid video is inspectable but
stays qa_review: integrity/readability is not semantic acceptance.

CI34285819509 runtime job failed before pytest: observed_head was abbreviated.
Corrected progress to full272d06cf74ddb45840d0f1456a6a6cf6336cd0c1; local goal
progress audit now passes. No tests skipped by that CI are claimed passed.
