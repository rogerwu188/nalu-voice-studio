# Video-review CI regression

Parent: `db32488ca55022507582965b8cd2c365de8edbe9`.
CI https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34179525437
reported 757 passing and two failing runtime tests. Both failures were
`test_video_review_is_bound_replayable_and_not_master_qa` (accept/concurrent):
the isolated preparation validator mock rejected the `_read_saved` keyword that
the accepted-video read path now passes. Production authorization was not the
failure and was not relaxed to fix it.

Updated the mock to explicitly match the validator signature. The video-review
suite and independent saved-read state-policy suite pass: 11 tests in 2.67s.
Ruff passes. This is targeted verification, not full-suite or native acceptance.
The replacement CI must still pass. SOP-04 remains IN_PROGRESS.

The supervisor observed `/goal` as `usageLimited`; this was not treated as
completion or as authorization to consume a reset. Safe repository work was
performed in this available turn. Next remains native sound-role selection and
mix/render connection, with the full product objective unchanged.
