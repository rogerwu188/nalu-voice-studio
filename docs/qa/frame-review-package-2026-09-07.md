# Frame-review package staging

Status: IN_PROGRESS — staging is not native interaction acceptance.

Candidate `26dddd69433ae95c34b7ef66fe81b880c98a6e6e`, CI
[34068985738](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34068985738).
At 2026-09-07 00:21 UTC the runtime and macOS ARM64 jobs succeeded;
Intel and the full workflow were not yet verified complete.

ARM64 artifact `9999962862` was downloaded. ZIP SHA-256 matched its packaged
checksum: `0e8c43be27ab4703aad08ab130000d373f12490853c7f95283c48268b46ff5f5`.
`codesign --verify --deep --strict` passed. The signature is **ad hoc**, with no
TeamIdentifier; this is not Developer ID signing or notarization.

Staged app: `/tmp/nalu-frame-review-qa.Ruu7Km/app/Nalu Voice Studio.app`.
Launch requested with isolated support directory
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-frame-review-support.gcJ53y`
and port `18789`. Existing apps and family data were not replaced. Runtime
readiness, synthetic frame setup, native accept/reject/error/switch states and
screenshots still require verification. Do not launch duplicate instances merely
because startup takes time.

The later accepted-frame dispatch binding is commit
`15dfb2063c7b4321ba9324cbe936ce137b2e571b`, confirmed pushed to main; its CI
`34069325621` was pending. It is **not** included in this older native artifact.
No real writer retry, provider generation or publication was performed here.

Native follow-up: the loopback readiness probe could not connect; the subsequent
native-app inspection reported that the Mac is locked and could not be unlocked
automatically. Manual unlock is required for native interaction QA. This is not
evidence of an app crash or failed frame workflow. Do not repeat launches or mark
the native check PASS; continue safe backend work while the screen is unavailable.
