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
