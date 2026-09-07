# Continuous shot tail input — IN_PROGRESS

Reviewed video preparation now supports a continuous shot using the preceding
accepted video's exact decoded final PNG. It supplies the professional
SAME_SCENE_CONTINUATION/PREVIOUS_ACCEPTED_FINAL_FRAME contract and preserves
director, aspect ratio, model and duration. New image approvals cannot substitute
for a tail. Scene-first shots cannot consume a tail.

Preparation validation binds the tail to the immediately preceding task in the
same approved plan. It validates decreasing shot lineage before recursive source
validation. Dispatch carries the tail identity and revalidates it before HTTP;
video review and subsequent tail extraction retain that identity as well.

The integration fixture now has an 8-second first shot and 7-second continuous
shot: confirmed frame → prepared first shot → synthetic MP4 → adoption → decoded
tail → second preparation. It checks exact frame hash, restart reuse, rejection
of image substitution/first-shot tail use, and failure after previous adoption is
revoked. No paid generation or real end-to-end claim is made.

CI regression discovered: f6e89d6 run 34087400061 failed on app.py import ordering.
The order is corrected here and full-repository Ruff passes. Local regressions
also exposed an old plan-only test that allowed continuous input without a tail;
it now verifies rejection and distinguishes isolated director compilation from
actual tail validation. Native playback commit 186f254 CI passed previously.

Still open: native adoption/tail selection controls, real provider continuation,
native playback/accessibility QA, episode assembly/master QA and controlled release.
This checkpoint is not an SOP PASS.

Final local regression: 135 passed in 55.54s (image review, shot planning, video
review, paid submitter boundary and goal progress). OpenAPI regenerated; current
CI and installed-app QA are still required.
