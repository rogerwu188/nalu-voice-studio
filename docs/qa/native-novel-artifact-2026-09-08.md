# Native artifact preparation — not installed acceptance

Downloaded the completed arm64 artifact from CI34263459180, commit
627d89ddfab2c1312183cf600933563e4eac3718, into `/tmp/nalu-native-qa-sLPxwo`.
The job passed; the full workflow was still running at the initial check.
Archive SHA256 matches its accompanying checksum:
`f20fe5f8c0f01716dfb9dd97c3bfca84141767aef3c18c7451b0475c6e789292`.

Extracted app:
`/tmp/nalu-native-qa-sLPxwo/extracted/Nalu Voice Studio.app`.
`codesign --verify --deep --strict --verbose=2` reports valid on disk and satisfies
its designated requirement. Executable is Mach-O arm64. Signature is **adhoc**, no
TeamIdentifier: this is NOT Developer ID signing, notarization or release acceptance.

No existing app was replaced or launched, and no user project was modified. This
candidate predates the d7c6d76 回-selection correction; do not call it current HEAD.
Next native QA must use isolated application support via the existing local-QA flags
and record the exact candidate. Local CLT compile blocker remains; CI artifacts are
the available native test route. Full input-to-script/video/release QA is still open.
