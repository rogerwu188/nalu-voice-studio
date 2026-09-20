# Current candidate native novel-reader QA

Candidate: `6f2e69a1e9d1b34e0956c153f6cb88281c050088` (CI
`35540824646`, all runtime/arm64/x86_64/universal jobs successful).

## Observed

- The downloaded arm64 artifact was checksum-verified and launched in an
  isolated local-QA support directory.
- The saved project loaded with `100 / 100` imported chapters and the reader
  disclosure opened normally.
- Chapter 1 displayed, and `下一章` changed the reader state to chapter 2 with
  a distinct saved body. Navigation did not dispatch a model/provider request.
- The app reached `本地制片厂在线 → 可以创作` and retained the prior saved
  conversation without automatically retrying its incomplete writer request.

## Important boundary

The isolated database was imported by the earlier candidate, so its persisted
chapter rows contain the earlier full-page extraction and still display some
Wikisource chrome. The new MediaWiki extractor is covered by unmocked HTTPS
reads and 45 regression tests, but this QA did not mutate old rows or falsely
replace their persisted digest. A fresh import using the current candidate is
still required to verify the cleaned text in the installed UI.

This proves current native artifact startup, persisted source recovery and
read-only chapter switching only. Interactive AI screenplay generation, video
episode production, final human review, signing/notarization and publication
remain incomplete.
