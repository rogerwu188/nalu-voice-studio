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

## Current build and full runtime regression

CI34286316710 on7ddce0c81308373d12b396c875d84e5385fb235a completed success
(arm64, x86_64, universal bundle and runtime). Local full pytest at the same
clean code revision passed800 tests in528.95s, with two dependency deprecation
warnings. This includes version-reader Swift CI but not native visual acceptance.
The artifact download is in progress at `/tmp/nalu-history-qa-7YdxCe`.
Isolated qv1poe20 SQLite still contains parent run_frame_review at qa_review and
child run_ddfaf60101144e24bf5b2f90b3961549 at preflight, ready for history QA.

## Native history inspection (partial, playback usability gap)

7ddce0c arm64 ZIP SHA256
`a330a21ecd129dead7a6e65899c94c043bb9aaa180726560a79221560a01a79f`.
Isolated qv1poe20 app successfully listed two versions; selected 第1版以前保存,
downloaded/validated the original seal and constructed VideoPlayer without crash.
The active progress remained30% preflight; after quitting, SQLite still had exactly
the same parent qa_review and child preflight. Owned runtime exited cleanly.

Actual screenshot showed the player below the fold, visible after scrolling.
The accessibility tree exposed no standalone playback control. Playback was NOT
verified: do not claim a completed viewing journey from successful file loading.
Next add explicit large, accessible play/pause controls, then one confirmation
pass on the native artifact. No provider calls, asset reuse or final-master QA
were performed by this test. Native finish review remains outstanding.

Playback-gap fix: added explicit large “从头播放这版视频” and “暂停视频” native
buttons above the player, with stable accessibility identifiers. The former
seeks to zero and plays; the latter pauses the existing local player. No additional
download, production action or acceptance write is attached. This follows the
existing edit-preview control and impeccable action-clarity guidance. Diff and
goal-progress checks pass; actual playback confirmation on a new bundle is pending.

Native f4366e1 artifact from CI34292299897 (whole workflow success) exercised
both explicit play and pause buttons on nel8waa9 original run_frame_review.
The sealed file opened, and screenshot after play showed the synthetic gray
picture with pillarboxing rather than the initial empty black player. No crash
or active-child change occurred. This proves button reachability and rendered
picture, not semantic film quality or measured audio/time progression. App quit
cleanly; no production or publication operation was attached to those controls.
