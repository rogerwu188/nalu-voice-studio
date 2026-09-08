# Native mix preparation and rendering transport

IN_PROGRESS, not a completed episode or SOP.

RuntimeClient now calls the existing adopted-dialogue prepare-mix and local
postproduction-materializations endpoints. Prepared input is bound to the dialogue
receipt, caption source and four exact selected sound layers; output geometry uses
the current default 1920x1080. The response bytes are preserved for explicit render
retry. No model-provider or publication call is added. Rendered results must match
run and episode; the receipt is not a master-acceptance claim.

Added native tests for exact body retention and changed staging, captions, size,
layers, requester and foreign-run result rejection. Native tests/CI have not yet
run for this change. Backend dialogue binding regression: 8 passed in 0.44s.
`git diff --check` passed. The test shot fixture is deliberately minimal: native
checks are context guards; full shot and source validation remains server-side.

The native selection panel now automatically prepares the currently confirmed
dialogue/captions and selected sounds, then offers a separate explicit render
confirmation. The model retains prepared bytes after an ambiguous render failure,
blocks input changes and re-preparation after submission, and prevents duplicate
submission after a verified result. Added injected native tests cover no implicit
render, timed-out retry with identical bytes, blocked replacement and completed
result no-op. These new native tests still require CI execution.

Large wrapping controls and status readback follow the incumbent Operate UI.
Backend dialogue-binding and rendered-output immutability regression:
36 passed in 22.16s (two dependency deprecation warnings). This includes existing
synthetic rendering/cancellation coverage, not execution of the new native UI.
Leaving the panel cancels client waiting, not server production; the message says
so explicitly. No installed or visual QA has been performed for this version.

Next: run-state recovery/cancellation, durable pending plan and video QA handoff. Installed
interaction, real recording/media production, master acceptance and release remain
unverified. Previous state CI was superseded (34254408000 cancelled), not passed.
