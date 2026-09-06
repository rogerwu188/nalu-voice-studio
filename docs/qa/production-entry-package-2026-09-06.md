# Production-entry package verification

Candidate: `7b9069fb3a90b01a9fda400c9ca13e1bb4feebaf`.
CI [34063554684](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34063554684)
completed successfully across Runtime, ARM64, Intel and Universal jobs. This
includes compiled native preparation/parser tests and packaged startup checks,
repairing the preceding missing-httpx startup failure.

ARM64 artifact 9998259459, downloaded to `/tmp/nalu-production-qa.tPCeEA/artifact`.
Inner ZIP SHA-256 matches its shipped checksum:
`6d6f29d8671929b3a82c7dcb622d9a74050e39775bb572a6d3997386239d70a1`.
Deep strict codesign verification passed (ad-hoc signature, not notarization).
App extracted to `/tmp/nalu-production-qa.tPCeEA/app/Nalu Voice Studio.app`.

Isolated database was backed up to `/tmp/nalu-production-qa.tPCeEA/pre-upgrade.sqlite3`
before launching the new package with the existing temporary QA directory and
port 18769. LaunchServices startup completed: `/health` returned status ok and
schema version 28. Native accessibility inspection showed the four existing
projects and local factory online. Selecting the synthetic two-episode project
restored its story/drafts, episode-one preflight at 30% and episode-two review at
15%. Read-only SQLite confirmed episode `ep_7b911d1b2d7041e1b3267be741c5aa2c`
approved revision 1, and `ep_2059c8fc397b48119046f9964b619c20` still unapproved.
The UI explicitly states no video is being generated. No microphone capture,
new script approval, paid request or publication was performed in this inspection.
This is bounded package startup/restoration QA, not live dictated-start QA.

Added two further native model tests through `commitTranscript`: missing approved
episode makes no request; duplicate in-flight start makes one POST and reports
preparation rather than video completion. Syntax parsed; these new tests require
their own CI run and are not covered by candidate 7b9069f.
