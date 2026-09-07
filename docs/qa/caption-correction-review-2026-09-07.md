# Recording caption correction checkpoint

Backend explicit correction/confirmation is implemented against the current
transcript digest and adopted recording. Corrected segments must fit its PCM
duration; saved confirmation uses a previous-review compare-and-swap and exact
retry returns the latest receipt. Source consent/adoption is checked again even
on retries. This is user attestation, not forced alignment or final-master QA.

Validation: `pytest tests/test_image_review.py -q -k video_assemble_stage`:
1 passed, 25 deselected (19.63s). Synthetic media fixture checks corrected save,
reopen/replay, stale digest, conflicting review, out-of-window timing, Origin
rejection and rejection after recording adoption is revoked. Ruff passed after
import formatting; OpenAPI regenerated.

Recovery follow-up: typed GET now returns the latest review and an explicit
current-transcript applicability flag. It revalidates adopted PCM, consent,
transcript/review digests and segment bounds without creating events. Historical
reviews remain available as concurrency predecessors but cannot approve a new
transcript. Regression fixture passed (21.53s): empty recovery, reopen recovery,
no write on GET, superseded transcript rejection, historical approval suppression,
and rejection after recording adoption withdrawal. Ruff passed; OpenAPI updated.

Pending: native correction UI, installed user QA, final mix/master
and release integration. CI for this checkpoint is not yet confirmed. No SOP
status is upgraded. No paid service, real family recording or release was used.
