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
