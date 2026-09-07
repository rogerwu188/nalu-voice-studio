# Native explicit edit-confirmation state — IN_PROGRESS

Added the native edit-review state model used by the forthcoming confirmation
controls. It loads current decisions, prepares a readback containing edited
duration and the limited scope of picture approval, and submits only on explicit
confirm. Preparing/reading/cancelling an unsubmitted decision performs no POST.

An uncertain submit retains its exact request, preview identity and expected
review ID. It cannot be silently cleared or replaced by the opposite decision.
Read-only recovery clears uncertainty only when it finds the exact matching
decision, or a newer authoritative decision superseding the expected version;
the latter asks for a fresh review rather than endlessly replaying a stale CAS.
No video generation, audio approval or publication occurs here.

Native tests cover unloaded guard, no-submit readback, 503 retention, prevention
of opposite/cancel while uncertain, unresolved GET recovery and same-request
successful retry. Current native CI is still required; no local native execution
or installed-user acceptance is claimed. Ruff services/tests/scripts and diff
check passed. Parent a616984 CI 34094480463 is pending and 037c846 CI 34094090038
is running; those observations do not establish current native test success.
The actual backend encode/review regression also passed again: 1 test in 7.59s.

Next: attach native readback/accept/reject/retry controls to the visible preview,
verify current CI and actual player/confirmation UX, then consume exact approved
edits in real postproduction, audio/caption alignment, master QA and release.

## Preview controls checkpoint — 2026-09-07

`EpisodeEditReviewPanel` is now attached immediately below the episode preview
player. It inherits native large buttons and Nalu typography, wraps status text,
and offers explicit adopt/reject, spoken readback, confirmation, retry and
read-only reconciliation. Appearance performs only GET. Controls are disabled
while busy; loading failure cannot enable adoption. Cancelling an unsubmitted
dialog preserves the existing recorded decision. Cancelling an uncertain retry
does not discard the pending request. Preview receipt/edit identity resets the
panel when the viewed cut changes; server validation remains authoritative.

Extended native state tests cover rejecting then cancelling without a POST or
changing the existing acceptance. The synthetic backend encode/review regression
passed again (1 test, 8.34s); scoped Ruff and git diff checks passed. These are not
real-provider production or user playback evidence.

Parent a616984 CI [34094480463](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34094480463)
passed Runtime, ARM, Intel and Universal jobs. The new controls and extended test
still require their own CI. Local Swift manifest linking remains broken, so no
local build or installed screenshot, keyboard, VoiceOver or player QA is claimed.
No installed app was replaced. SOP remains IN_PROGRESS.

Next: verify current native CI and installed player/confirmation when a usable
build is available; connect the exact approved edit to actual audio/caption
postproduction and master QA. Do not equate picture adoption with final release.
