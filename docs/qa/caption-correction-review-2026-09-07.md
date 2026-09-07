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

Native transport follow-up: typed caption submission, receipt and recovery now
validate current transcript identity, source PCM/review binding, exact echoed
corrections and non-master flags. Historical recovery cannot be exposed as a
current approval. Added native boundary/serialization test source. Native tests
have NOT run locally (existing Swift toolchain blocker); CI is required. Ruff,
progress-file audit and diff checks passed; these do not prove Swift execution.
Next wire the interaction state and visible correction controls.

Native UI follow-up: RecordingCaptionModel/Panel now connect recovery, retained
text corrections, readback, explicit confirmation and exact pending-request
retry inside the adopted-recording panel. Timing remains unchanged during text
correction. Initial recovery restores previously corrected timing/text; later
refresh preserves local edits. Cancel before any submission unlocks editing;
uncertain submissions remain retained for reconciliation/retry. Source change
recreates the panel using transcript ID. Impeccable hardening guided retained
inputs, explicit labels and existing native large-button styling.

Validation in this follow-up is source review, Ruff and diff checks only. Local
Swift compiler remains blocked; CI and installed keyboard/VoiceOver/long-text
QA, model state tests and voice-driven correction are still outstanding. No
claim that these controls are deployed to the installed application.

State-test follow-up: EpisodeShotPlanTests now drives the caption model through
empty recovery, edited draft, cancel-before-submit, failed save, exact request
retry, reopening confirmed text, preserving edits on refresh, and GET-only
reconciliation of an uncertain save. Native test execution remains pending CI.
Backend synthetic media regression passed again (21.60s); Ruff/diff passed.
CI 34106043111 for c1640ce completed successfully in runtime, macos-arm64,
macos-x86_64 and macos-universal. This result predates the native caption UI and
does not prove that UI passes. Current UI CI 34106778965 was in progress.
