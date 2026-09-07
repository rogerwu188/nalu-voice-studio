# Native video review bridge — IN_PROGRESS

Added typed adoption/rejection drafts and receipts, credential-free local latest
review recovery, and native submission of the exact materialization/preparation
and previous-review ID. Responses must match the run, task, provider binding,
request, video digest, candidate, decision and confirmation. Inconsistent approval
flags and fabricated billing/master/semantic QA are rejected. Review recovery
retains the latest shot decision even if it concerns another candidate; it must
not be displayed as adoption of the current preview.

Native URLProtocol tests cover GET recovery versus POST decision, exact previous
review ID in the submitted body, no provider keys, foreign candidates and
inconsistent decisions. These tests await macOS CI; local Swift remains blocked
by the recorded toolchain manifest/module problems. Backend image/video/progress
regression: 32 passed in 15.12s.

Parent c3405fb CI 34088470406 in progress. Prior 9eaad65 CI 34087784562 failed on
the same import ordering already fixed in c3405fb; no new failure inferred.

Not complete: native adoption controls and spoken confirmation, native tail
selection/next-shot preparation, installed-app playback QA and full real episode
production/master/release acceptance. This bridge alone closes no SOP.
