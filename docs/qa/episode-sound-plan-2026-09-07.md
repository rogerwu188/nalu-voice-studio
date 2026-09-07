# Confirmed episode sound/caption draft — IN_PROGRESS

Backend POST `production-runs/{run_id}/sound-plan-drafts` derives timed sound
cues and SRT drafts from the current confirmed shot plan. It verifies the plan
hash, current production snapshot, approved script content/revision and episode
duration under a SQLite writer lock. Native requests carry only the expected
plan hash, not API keys or professional audio fields. Restart/concurrent replay
returns the same event; stale plans, changed scripts and archived projects reject.

Cues retain the confirmed narration and sound direction. Empty narration creates
no invented captions. Caption text is escaped and timed to shot boundaries, not
claimed to be speech-aligned. Five required audio layers are listed, but recordings,
speaker identity/authorization, alignment, caption approval and master acceptance
remain explicitly absent/false. No network, generation, spending or run transition.

50 tests passed in 13.16s across image review (including six sound-plan cases),
video materialization and bounded video download. Cases cover precise 8+7 second
caption windows, empty narration, escaping, stale hash/plan/script, archive,
Origin/extra-field rejection, restart and concurrent deduplication.
CI-scope `ruff check services tests scripts` passed; OpenAPI regenerated.
An overly broad `ruff check .` also scanned vendored Qingshan and reported 5,123
findings; vendor code was not edited, and no repository-wide lint PASS is claimed.

Integration gap discovered: accepted episode staging carries unedited whole-source
windows, but existing Qingshan postproduction explicitly forbids whole-provider
passthrough. Staging now marks editorial selection incomplete and sources unedited.
Do not pass those windows off as a render-ready edit or weaken that gate. Real
editorial selection/retiming, verified workspace/receipts, five authored audio
layers, aligned captions, native interaction, rendered master QA and release
are still required. This backend draft is not completed postproduction or real E2E.

Parent af11563 full CI succeeded:
https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34090041530
Current checkpoint CI and installed-app QA still required. No SOP promoted to PASS.
