# Bounded on-device speech waits — 2026-09-07

The shared Apple Speech recognizer now uses a one-shot callback waiter. Permission
waiting is bounded to 120 seconds and recognition to 180 seconds. Task cancellation
resumes the caller and cancels recognition even if Apple never calls back.
Duplicate/late callbacks are ignored after completion; waiter reuse is rejected.
The app cannot dismiss macOS's authorization dialog: timeout ends only its wait.

This applies to recording transcription and final-master speech QA, without
changing TTS or switching to cloud recognition. Temporary recording cleanup can
run on timeout/cancellation instead of waiting indefinitely.

Added native test source for duplicate results, missing-callback timeout,
cancellation with a late result, one-time cleanup and rejected waiter reuse.
Native execution remains pending CI due to the recorded local toolchain problem.
Ruff/diff checks passed; these do not prove native execution. CI 34104369487 was
running at inspection. Live authorization/ASR and installed UI QA remain open.

Next: visible transcript start/save/recovery actions, explicit subtitle review
and final mix/master. No SOP status upgraded.
