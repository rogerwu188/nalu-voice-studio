# Native approved sound-timing orchestration — IN_PROGRESS

After an explicit edit acceptance succeeds, the native model now prepares the
sound/caption draft using that exact review ID. Transport validates the current
edit/review context before sending and requires approved-edit timing, matching
review ID, exact duration and unapproved audio/caption/master flags in the reply.
The existing pre-approval edit-save route still requires draft-only timing.

Review acceptance is committed to model state before the second request. A sound
failure keeps the accepted review, clears review uncertainty and identifies the
unsynced postproduction step. `retrySoundPreparation` repeats only local sound
preparation, never the review POST. Native tests cover 503 partial failure and
successful exact-review retry. They are added, not yet executed on this commit.
The retry method still needs its visible control/restart recovery entry; do not
claim that this source checkpoint is an installed complete user journey.

Backend synthetic encode/review regression passed (1 test, 10.59s), scoped Ruff
and diff checks passed. Parent state-model CI 34094904074 has passed ARM, Intel
and Universal jobs; Runtime remains in progress. Current changes require their
own CI. Local Swift manifest linking is still unavailable and the installed app
has not been replaced. No paid call, voice recording, authored sound layer,
caption alignment, master or release was produced by this checkpoint.

Next: expose postproduction retry/recovery without another edit confirmation,
verify native CI and installed QA, and continue actual sound/caption/master work.

## Visible recovery checkpoint

The preview panel now replaces the already-accepted edit action with “继续准备
配音和字幕”, or “重试准备配音和字幕” after partial failure. This uses the
sound-only retry method and reads its result aloud using the incumbent callback.
It does not resubmit the edit decision. The user can still explicitly request a
different edit. Controls remain native, large and consistent with the adjacent
VideoReviewPanel; status text wraps and a busy indicator labels ongoing work.
Impeccable hardening guidance informed disabled/recovery states, not a redesign.

On reopening the preview panel, the existing read-only confirmation load restores
the accepted review and enables the same continuation control. A failed reload
disables continuation even if an earlier in-memory acceptance remains. Newly
added native tests verify GET-only restoration, sound-only continuation and no
request after failed recovery. Opening the panel never starts paid production.

Checks: synthetic backend preview/review regression passed again (1 test, 7.69s),
scoped Ruff and diff passed. State-model CI 34094904074 remains in progress;
ba811ec CI 34096325134 was pending at inspection. No current UI screenshot or
VoiceOver/keyboard/installed QA is claimed because the local build toolchain
remains unavailable; native tests still need current CI. These controls prepare
timing drafts only, not actual recordings or an accepted master.

Next: connect real authored audio inputs and subtitle alignment to the approved
timing; verify current CI and installed native workflow without treating this
checkpoint as product completion.
