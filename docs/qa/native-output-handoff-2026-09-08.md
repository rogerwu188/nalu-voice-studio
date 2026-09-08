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

## Positive technical render handoff

Added a second adopted-render case with deterministic per-frame changing pixels
at24fps. It follows the same actual encoding, replay, four-artifact seal,
structural and decoded QA endpoints. Passed in118.60s: both technical gates PASS,
while the run remains QA_REVIEW; consent revocation still blocks further access.
The low-frame-rate rejection case remains separate; no QA thresholds were changed.
15 video-reader tests also passed in0.27s; ruff passes. Random-pixel test imagery
is not narrative footage and proves no creative, semantic, human or release QA.

CI34267285622 on05330f3 reports Swift tests successful for both architectures;
the complete workflow was still running when inspected. Native installed
failure recovery and real production acceptance remain open.

## Distinguish known quality failure from unknown transport outcome

Native validated, hash-bound FAIL reports now throw a dedicated quality error.
The mix model preserves the exact plan and leaves result unset while explaining
that the video exists but needs repair, rather than implying the user must retell
their story. Known repeated-frame failure has specific plain-language copy;
unrecognized diagnostic text is never directly surfaced. Timeout/integrity/unknown
status remains the separate unverified-outcome path. Added native error-copy and
model-state tests; CI execution and installed layout/speech inspection pending.
Impeccable clarify guidance informed the distinction; no visual redesign.
The actual repair action and retry-button behavior still need integration.

## Native repair-plan recovery

After a validated FAIL report, native transport now reads the existing repair
plan and requires matching run, seal and master identities plus blocking tasks.
Unavailable/stale plans are not attached, but cannot turn a known quality failure
into an unknown transport error. The mix model retains the validated plan for
the repair flow and clears it on successful QA. Added binding tests; native CI
pending. Repair presentation, explicit new-version production and durable native
reopening remain incomplete. No paid generation or publication is invoked.

## Cross-flow revalidation and progress correction

At73c8849, OpenAPI check is current and52 combined interactive-story, writer,
novel-import and output-immutability tests passed in37.13s. Full CI34267285622
passed on05330f3 (initial native handoff), not on latest repair retrieval.
Corrected stale GOAL_PROGRESS entries claiming handoff/candidate persistence had
not been implemented. Next work remains native failure/reopen recovery, repair
presentation/new-version production, semantic/human QA and installed source journey.
No completion status change, paid call or release action.
