# Current-episode production voice entry

Status: IN_PROGRESS, following `bd87c9c5c439b401b895bd3eda89e38936e19002`.

The native production command handler previously supported pause/resume but not
starting preparation. Explicit current-episode phrases now call local QingShan
preparation only after the selected episode has an approved script revision.
The POST is always dry-run with paid approval false, with a stable per-episode,
per-approved-revision idempotency key. It refreshes progress and does not claim a
finished video. Negations, questions and all-episode requests are not start commands.

Added native parser, decoded approval and URLProtocol request tests. Swift syntax
parsing passed; actual compiled tests and packaged native QA remain pending CI.
The preceding writer-observation checkpoint passed all 350 Python tests in 190.49s.

CI 34063086327 failed packaged Runtime startup on both macOS architectures:
`ModuleNotFoundError: No module named 'httpx'`. The new writer transport imported
a previously dev-only dependency. Moved httpx into production dependencies so
the standard packaging install includes it. This is a diagnosed regression and
source fix, not yet a proven repaired installed build.

Real paid submission approval UI/voice flow and generated video delivery remain
open. This entry is an implementation step toward them, not a replacement for
them or a completed SOP.
