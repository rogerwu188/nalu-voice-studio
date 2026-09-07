# Accepted first-frame to video request binding

Status: IN_PROGRESS; runtime/mock integration, not paid video success.

Once a task has an interactive image preparation or review, video preparation
requires its latest accepted frame review ID. The runtime checks that review's
digest, image bytes hash, current approved shot plan, materialization and source
image preparation. Missing/rejected/superseded decisions, substituted frames and
inconsistent source records are rejected. Existing professional imports without
interactive image records continue through their full opening-anchor contracts.

The saved video preparation includes the review ID/digest and materialization ID.
Dispatch reconstructs that binding from the saved preparation, validates it again,
and rechecks immediately before the provider POST. This does not grant missing
professional QA or cost approval; the existing paid-production gates still apply.

Tests extend actual fixture image review to exercise accepted/rejected images,
changed bytes, absent review IDs and later decisions. A full mock paid-dispatch
case also carries a synthetic reviewed-image chain through reservation/submission.
Initial affected suite 89 passed; final frame/review subset 12 passed. Real image,
real billing, real video and native first-frame QA remain outstanding.
Full local suite: 499 passed in 64.61 seconds. Final source-binding additions were
also covered by the 12-test subset. Ruff, OpenAPI compatibility and progress
structure checks passed; they do not establish a completed native or paid workflow.

CI sequencing note: native UI candidate `26dddd6`, run `34068985738`, was pending
behind `6ce796b` when observed. Do not push another checkpoint while it is the sole
pending run: GitHub replaces pending runs even when running-main cancellation is
disabled. Local work/commit can continue; push after that native run starts so its
compiled tests and installation artifact can actually be obtained.
