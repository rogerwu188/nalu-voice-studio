# Native sound-source transport

Parent `52e5a0d3a48405ab95761ec9af9b2f059210e012` passed CI:
https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34180565640 .
The earlier video-review CI regression is resolved for that commit.

The native RuntimeClient now posts typed sound-role asset selections to the
existing sound-sources endpoint. It checks the current approved sound plan,
finite offsets/gains and response binding to the exact run, asset, role,
duration, cue count and managed source path. Returned sources are Codable for
the downstream mix request. This performs no paid generation and does not
claim music or final video approval.

Added native tests for matching receipt/source roundtrip and rejection of
changed role, asset, duration, consent identity, path, gain, source hash, cue
inventory or a premature master-accepted flag. Numeric edge cases are covered.
These tests still require native CI execution; no installed QA claim is made.
Backend source/binding regressions: 22 passed in 0.91s; diff check passed.

Next: connect native asset choices and these receipts into mix preparation and
render action; preserve pending selections/retries and avoid professional forms.
Missing soundtrack generation, installed QA and final release remain open.
