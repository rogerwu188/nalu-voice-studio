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
