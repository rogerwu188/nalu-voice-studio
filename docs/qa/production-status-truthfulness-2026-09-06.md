# Production status truthfulness

SOP-08 remains IN_PROGRESS.

Native 680256b QA showed the isolated dry-run preflight fixture at 30% with
“Nalu 正在工作，没有停”. The backend `RUN_PROGRESS` maps preflight to a passed
local preflight; it does not establish a running generation worker. The native
presentation had grouped created, preflight, queued, running and qa_review as
working, so its moving icon and reassurance overstated activity.

The presentation now distinguishes created/preflight/queued as waiting, qa_review
as needing review, and running as working. Queue cancellation guidance respects
canCancel; verification remains offered for qa_review with a run ID. Existing
charge-reconciliation, approval, failed/cancelled and completed branches remain.
Preflight wording refers to the current stage, not a claim that no prior generation
ever existed before recovery. This is no change to execution or charging policy.

Tests cover preflight, created/queued, QA review with no working animation, and
retained running/cancellation/approval/reconciliation behavior. Syntax/diff checks
pass; compiled CI and native visual confirmation remain open. The prior screenshot
is evidence of the defect, not evidence that the new UI passes.
