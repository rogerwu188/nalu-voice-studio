# Native saved-edit to sound-draft handoff — IN_PROGRESS

Successful native edit save now submits the saved edit ID/hash and confirmed plan
hash to the local sound-plan endpoint. The reply must match the edit, run, plan,
duration and draft timing basis and must not claim audio generation, alignment,
approval or master acceptance. No keys or provider requests are involved.

The saved edit is retained before retiming starts. Retiming failures and foreign
receipts therefore report a partial success (edit saved, sound timing not synced)
rather than saying the edit itself failed or discarding the local cuts. Explicit
save retry reuses the same edit identity through backend deduplication. Native
tests cover retiming failure, exact edit ID/hash, successful timing handoff and
wrong-edit rejection while retaining the saved edit. Those tests await native CI.

Seven focused backend regressions passed in 6.21s (sound drafts and real-decoder
two-shot edit fixture); Ruff services/tests/scripts and diff check passed.
Local native execution remains blocked by the previously reproduced Swift
manifest linker error; no installed UI QA or native test success is claimed.
9802db8 CI 34091496570 has successful ARM, Intel and runtime jobs; Universal was
uploading its artifact. 503c6fb CI 34092538522 is in progress, not failed/stopped.

Next: actual trimmed video preview, explicit edit/duration confirmation, real
recordings/alignment, complete postproduction/master QA and controlled release.
Draft timing is neither speech alignment nor final subtitle acceptance.
