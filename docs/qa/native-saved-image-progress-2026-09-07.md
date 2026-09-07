# Native accepted-image task progression

Status: IN_PROGRESS. Source implementation and test fixtures are not compiled or
native end-to-end acceptance.

The native frame/reference loader previously ignored accepted image submissions
and only looked for already downloaded results. It now advances the exact saved
submission when no matching local image exists: one read-only provider task query,
then the existing bounded downloader, then exact-byte preview. Pending and failed
tasks have distinct messages. The existing reload action queries the same task.
Uncertain submissions are never retried. Cached frames do not read credentials or
query the provider. Cancelled view tasks do not continue into preview.

The credential is read off the main actor without prompting for authentication
and sent only to the owned runtime advance endpoint. It is not sent to event,
preparation, content or review endpoints. No generation endpoint or new paid
approval is introduced. The client checks run/submission/result binding before
making a frame reviewable; the backend retains its authoritative hash checks.

Follow-up at 2026-09-07T01:28:05Z: cumulative source `1dd7962`, CI
[34072916544](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34072916544),
passed the ARM64 Swift test step. Other build/test jobs were still active, not
completed acceptance. Preceding reference UI source `883c902` now has a complete
successful CI run 34072165394. CUA independently reported that the Mac was locked
and automatic unlock failed; current native interaction remains blocked on unlock.
No screenshot or human-use PASS is recorded.

New Swift URLProtocol cases cover accepted completion and cached reuse, waiting,
failure, foreign-run response, uncertain submission, unavailable credential and
stale request. These are synthetic protocol fixtures, not provider evidence.
Swift execution is pending CI because the local toolchain failure was already
verified. Native app interaction and real provider results remain unverified.

Runtime progress/reference regression: 29 passed in 22.46s. Source commit
`9250389` was pushed; its cumulative CI is
[34072890819](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34072890819)
(pending at 2026-09-07T01:24:10Z). The queued predecessor run for `7ffeb9b`
was superseded/cancelled, not passed. No current-candidate CI completion is claimed.

The preceding native reference commit `883c902` passed both Swift test jobs in CI
run 34072165394; the complete run was still active when inspected. This does not
verify the new progress code. No paid image/video call occurred in this checkpoint.

Next: compile and exercise the progress path in an isolated native candidate;
complete concrete reference authority/verified image prices and spending review,
then real image → per-episode video → master → controlled release. Do not replace
the user's narration/online-source writing priority with voice polish.
