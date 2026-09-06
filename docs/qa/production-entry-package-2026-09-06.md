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
port 18769. Startup/restoration inspection is in progress, not yet reported PASS.

Added two further native model tests through `commitTranscript`: missing approved
episode makes no request; duplicate in-flight start makes one POST and reports
preparation rather than video completion. Syntax parsed; these new tests require
their own CI run and are not covered by candidate 7b9069f.
