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

## Isolated native launch and project creation

Launched this exact downloaded executable with NALU_ENABLE_LOCAL_QA=1,
NALU_LOCAL_QA_APPLICATION_SUPPORT pointing to
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/tmp.mDYNkkBYNS`, port18767.
Native UI initially displayed startup, then visibly showed green local-factory online.
GET /health returned status ok/version0.1.0/schema28. Clicked the actual native
“创建新项目” button through accessibility: sidebar immediately displayed 未命名故事,
planned6episodes; conversation invited a story or online materials. Runtime log
confirms POST /v1/projects201 and subsequent project assets/story/seasons reads200.
Test project ID: prj_ec436df733e142bb84505e006eb3f4ec. Bottom microphone control was
visible in the screenshot at the default window size. No text/URL input field was
present in this visible state. No microphone was activated; no provider call occurred.

Quit this isolated app through its UI. Its owned Uvicorn process19659 shut down
cleanly and port18767 has no listener. Temporary test database is preserved, not
deleted; existing app installation and normal user data were not replaced.
This proves native launch, owned runtime lifecycle and sidebar project creation only.
It does NOT prove spoken import, URL entry, full-book/script/video/release acceptance.
