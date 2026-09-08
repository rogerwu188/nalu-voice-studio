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

Next: wire a frozen prepare/render action into the selection panel, explicit
confirmation, run-state recovery/cancellation and video QA handoff. Installed
interaction, real recording/media production, master acceptance and release remain
unverified. Previous state CI was superseded (34254408000 cancelled), not passed.
