# Native output QA handoff — IN_PROGRESS

RuntimeClient.renderEpisodeMix now follows materialization with output sealing
of master, captions, postproduction manifest and shot manifest, then structural
and decoded-media QA. Reports must match run, seal and rendered master hashes
and report PASS. Failure throws to the existing recoverable exact-plan retry UI;
no final approval, speech QA, human acceptance or publication is performed.

Added deterministic seal-body and missing/unsafe-artifact native tests. Local
Swift toolchain remains incompatible; tests have not yet executed. Transport
failure/restart and actual encoded render-to-seal-to-QA fixture coverage remain
required. Existing renderer replay is idempotent, but full native recovery is
not yet accepted. No SOP promotion and no paid call.

## Actual render handoff uncovered replay bug

Extended the encoded adopted-media fixture to seal all four outputs, replay the
seal, then execute both prerequisite QA endpoints. First run failed: engine file
comparison recognized an exact replay, but repository event recovery rejected an
already-recorded event. Fixed reuse only when manifest path/hash/artifact count
match.28 output-immutability tests passed in22.56s; changed-file recovery remains
rejected and exact retry returns the same seal without another event.

Second encoded run passed sealing/replay and structural QA, then correctly failed
decoded QA with VIDEO_FRAME_REPEAT_EXCESSIVE. The fixture supplies low-frame-rate
synthetic video normalized to24fps; this is not acceptable final footage. The test
now asserts this specific failure and retained QA_REVIEW status, not a weaker
production threshold. A positive actual-footage QA handoff is still required.
Prior ef9f62d full CI34266785218 passed; this change/native05330f3 not yet accepted.

Final negative-handoff regression passed in95.74s: real encoding, exact seal replay,
structural PASS, specific decoded FAIL, retained QA_REVIEW, unchanged master bytes,
and subsequent consent-revocation rejection. This is a passing rejection test,
not a passing video or release.
