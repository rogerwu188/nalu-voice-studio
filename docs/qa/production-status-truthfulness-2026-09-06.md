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

## Bounded native verification

Source `4e03c16a16183eaaf53f7ee9a0582ee3b1457614`, CI `34054486473` all jobs
successful, arm64 artifact `9995568082`, ZIP SHA-256
`830baa0275a3932f58cbd0139f3693d62173ff90b0faec159a8e76618fb47cdf`.
Archive checksum/ad-hoc signature/entitlements verified. Native process 86544
loaded the existing local dry-run fixture. The
[actual window](images/native-preflight-waiting-2026-09-06.png) shows a waiting
clock icon and “本地预检已完成，当前未在生成视频”, replacing the earlier working
claim. Unit tests establish the non-moving presentation branch; a still screenshot
alone cannot prove absence of motion. No production or paid call was initiated.
This closes this preflight-presentation checkpoint only, not whole SOP-08.
