# Core-flow alignment correction

Full project remains incomplete. Source inspection found priority drift: repeated
sound-role/retry work without installed evidence of either requested writing-to-
release journey. Requiring elderly users to supply all four professional sound
roles is not the intended product; do not expand that UI as the default journey.

Trace: commitTranscript -> AssistantActionRouter -> web research / source text ->
saved source context -> requestsSourceWriting -> handleInteractiveStoryInput ->
writer -> unapproved episode drafts -> adoptInteractiveDraft. Narration enters
handleInteractiveStoryInput directly. Live Hops evidence still shows HTTP 401;
no new paid request was issued. That blocker must not be disguised as completion.

A concrete handoff defect: the user's “作为整个剧本” and “做成一部连续剧”
phrases were not matched, so successful lookup would stop before requested writing.
Added matching and negative cases (only search / don't adapt), plus whitespace and
webpage routing. Native tests added, not yet executed. This is a bounded routing
fix, not proof of semantic intent coverage, actual retrieval or writer success.

Previously pending backend work was retained, not expanded: exact prepared mixes
are saved in local SQLite run events with read-only recovery. Synthetic full-render
test passed in 92.48s, including separately opened app recovery, deduplication,
A-B-A latest-choice restoration and stale-plan rejection. Initial run used an
incorrect fixture variable; rerun passed after correction. Eight binding tests
passed separately; OpenAPI export and compatibility with prior HEAD pass.

CI 34253996299 on 1787c600c45387c91ead76b137d57997769e7834 completed successfully.
It does not validate subsequent source-selection/mix/UI changes.

Before each next checkpoint: identify which requested user-journey step is blocked,
inspect its actual route, fix that blocker, and record whether evidence is native,
real-provider or synthetic. Do not substitute module tests for installed end-to-end
proof. Next priority is executing both story inputs and tracing their first failure,
then same-project draft revision/approval and episode production, not voice polish.

## Input-to-review API journey check

`tests/test_story_to_review_journey.py` exercises both narrated and webpage-backed
inputs through public Runtime APIs: two generated episode drafts, a correction to
episode one, process/app re-creation over SQLite, unchanged episode two, per-episode
writer receipt reconciliation and explicit script approval. No SQL status edits,
direct answer injection for writer output or production dry-run is used in this
new check. Both cases passed in 1.25s. Source reading and provider responses remain
explicit mocks, so this proves application data handoff, not live model output or
installed voice interaction. No new production bug was demonstrated by these cases.

CI 34254979644 (277a13a4068149ccfe9bb29ac53054cc7b1a079b) completed its arm64
`swift test` step successfully; full CI remains running. This validates the older
native mix/state tests, not the newer natural-language routing fix. Next evidence
needed is installed current-client input/review execution and real-provider access,
then production entry without professional manual intervention.

## Current-client regression and next delivery gap

CI 34254979644 on 277a13a is now fully successful, not current-release proof.
CI 34256325262 on 8cc3aad arm64 job 102163168157 failed one of 152 XCTest
cases: `找到这篇文章，做成一部连续剧` passed the writing-intent check but failed
the separate lookup router. Added bounded source lookup plus writing-intent routing,
retaining negative tests for ordinary reminiscence and adapting the user's own article.
`git diff --check` passes; patched native execution awaits CI. The local CLT's duplicate
SwiftBridging module definitions remain unchanged; no system-tool workaround attempted.

Inspection also identifies a concrete next downstream gap: EpisodeMixModel only
records the rendered result. Native code has no rendered-output-seal request, while
verifyFinalMaster immediately downloads a sealed master. Semantic QA further requires
a sealed shot manifest and prior structure/decoded QA. Do not merely add a success
notice or seal three files and claim this journey works: connect the complete local
render-to-QA handoff and validate its produced evidence before native acceptance.
No new paid calls, publication, app installation or final acceptance occurred here.

## Encoded shot-boundary input

The local renderer now emits a digest-bound shot-boundary artifact from its actual
normalized timeline, master hash and plan hash. The hard-cut/continuous-mix contract
describes this executor, not a claim of creative approval or QA PASS. Visual change
is required at cuts; identical boundary frames remain a detectable QA failure.
The synthetic crash/restart rendering test decodes the resulting master through
inspect_shot_boundaries, verifies artifact-tamper rejection and old v1 result recovery.
It passes in 5.17s. OpenAPI compatibility with 9428282 passes. Full CI and native
render-to-seal/QA orchestration remain open; this is not end-to-end completion.

User added full web-novel import: find source, fetch accessible chapter text in order,
persist locally with resumable progress, then use it for episode writing. The current
source_reader only returns a 24,000-character single-page excerpt and discovers no
chapters: it does not meet this requirement. Build proper chapter import without
adding a copyright form gate, while respecting login/paywall/access boundaries.
