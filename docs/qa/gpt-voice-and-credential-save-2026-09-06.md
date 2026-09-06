# GPT voice entry and credential completion fix

User reported entering OpenAI credentials and selecting Done. The screenshot
still showed Not configured. Code inspection confirmed Done only dismissed the
sheet; reopening cleared drafts. Native UI and scoped Keychain lookup both found
no saved OpenAI item. No key was printed, no audio uploaded and no API call made.

Changes:

- Save and Done persists nonblank drafts before closing; unrelated empty SD2/H3
  fields are optional and leave existing keys untouched.
- Keychain writes are read back and compared in memory. Errors remain visible
  in the credential sheet; failed drafts are retained and the sheet stays open.
- GPT Realtime is the default bottom action. Local dictation/read-aloud is an
  explicitly selected alternate mode. Switching to GPT stops local capture/TTS;
  disconnected GPT does not silently enable system speech.
- Suppressed local readback reports incomplete rather than granting review credit.
- The default Realtime time limit is five minutes; cloud/guardian/key consent
  gates remain intact. No automatic paid connection occurs on launch.

Six native regression tests cover routing, suppressed readback, OpenAI-only save,
blank drafts and failed saves. Local Swift syntax parse/diff checks pass; full
Swift build/tests and native layout/save validation await CI and the new binary.
Actual Realtime speech, interruption and cost acceptance remain open. A user
authorized one at-most-five-minute session, but the key must first be saved.
SD2/H3 credential use from Task2-1 is separately authorized; its configuration
location is not yet resolved and no video generation has been submitted.

## Follow-up 2026-09-06T18:00Z

- User re-entered and explicitly saved OpenAI credentials in the running old
  application. A scoped Keychain existence check passed. No credential value
  was printed or stored in the repository.
- One read-only request to `GET /v1/models/gpt-realtime-2.1`, using the saved
  credential in memory, returned HTTP 401. This establishes an authentication
  blocker, not its exact cause. No audio was captured/uploaded and no generation
  or Realtime session was started. Do not retry paid sessions until resolved.
- Product commit `7879bd23ef93a481779f650c06ad88ff5da6776b` passed all four jobs
  in [CI 34050040349](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34050040349).
  Native deployment and interaction acceptance of that artifact remain pending.
- Follow-up code distinguishes HTTP 401, 403 and 429 with actionable fixed
  messages, without rendering provider response bodies. Regression assertions
  and Swift syntax parsing pass; this follow-up still needs full CI/native QA.

## Provider address correction

User then specified `https://hopsapi.com/v1`. A single read-only `/models`
request to that exact host with redirects refused returned HTTP 200 and three
models, none with `realtime` in its ID. The earlier official-host 401 is **not**
evidence that this credential is invalid at the intended provider. No key change
is requested and no generation/audio request was made to either provider.

The credential sheet now includes a validated HTTPS `/v1` address. Responses,
Realtime client-secret creation and WebRTC calls route to the selected address;
the two Realtime stages use a captured endpoint for the connection attempt.
Redirects are refused to avoid forwarding credentials to another destination.
The microphone consent sheet discloses the selected provider address and usage.
Provider Realtime support, CORS, model availability and native packaged QA remain
unverified. Endpoint routing/invalid URL tests added; syntax parsing passes.

## Connection-check follow-up

The native settings sheet adds an explicit read-only model-list check against
the entered address, using the entered key or the saved key. It never starts
recording, requests generation, or saves an entered draft implicitly. Results
are discarded if the address/key changes while the request is in flight.
Provider model IDs are bounded and rendered as text, with credential echoes and
markup excluded. The response stream is capped at 1 MB with request/resource
timeouts; redirects remain refused. The result explicitly does not certify
Responses, web-search tools or Realtime compatibility. The settings body scrolls
independently of the fixed Save and Done action.

Regression cases cover malformed/oversized lists, credential/markup filtering,
and avoiding false Realtime acceptance. Swift syntax and diff checks pass;
full build and native interaction QA are still required.

Read-only provider follow-up: `/models` returned HTTP 200 with IDs
`claude-fable-5`, `claude-fable-5-1`, and `gpt-6-astra`. Neither the configured
`gpt-realtime-2.1` nor research `gpt-5.4-mini` was listed. This is a concrete
compatibility gap to resolve, not definitive proof that every unlisted model or
endpoint is unavailable. Do not silently substitute models or claim Realtime
works. No generation was requested. The `/goal` was confirmed active after the
user resumed it; CI 34050705052 is the build for connection-check source
`3fdc8c664a6b5425755a528441f4847a1cd7489b`.

## Native provider verification — 2026-09-06T18:14Z

- Exact arm64 artifact `9994490351` from CI `34050705052`, source
  `3fdc8c664a6b5425755a528441f4847a1cd7489b`, archive SHA-256
  `5ec17a195208f32895ed484be5a788ce5a8c93217bf1632fc9cd3db67238d2ec`
  matches its packaged checksum. Code signature verification succeeded (ad hoc,
  not Developer ID/notarization). The release verifier also printed a missing
  speech-entitlement extraction warning while exiting zero; this needs separate
  investigation and is not recorded as a clean release acceptance.
- Launched isolated native process 78287 with a fresh temporary database and
  port 18767. `/health` returns ok, schema 27. Existing process 74041 and its
  project data were not terminated or overwritten.
- The new sheet recognized the existing saved key. No secret was entered,
  copied into logs, or changed. SD2/H3 stayed unconfigured.
- Pasted user-requested `https://hopsapi.com/v1` into the address field through
  native input; Save and Done closed the sheet. Reopening reads the identical
  address, also present in the app preference. Clipboard contents were restored.
- Native Check Connection returned 15 models using the saved key. This is a
  real app request, not only command-line evidence. No audio capture or generation.
- At 1100x736 window bounds, the settings body scrolls and Save and Done stays
  visible. [Screenshot](images/native-provider-connection-2026-09-06.png) contains
  no secret. The model-result body extends below the current scroll viewport;
  it is not all visible simultaneously. Human accessibility QA remains open.
- Both architecture jobs and Universal job passed; Runtime offline E2E step
  still running at observation. Do not claim full CI until it is terminal.

The user clarified the full SOP objective never changed. Model configuration
updates are progress reports, not completion of the Nalu product objective.

Final CI observation: run 34050705052 completed success (all four jobs). Direct
codesign inspection confirms the semantic recognizer does contain both boolean
audio-input and speech-recognition entitlements. The warning is reproducible in
the verifier's `plutil -extract` handling of the dotted entitlement key; do not
describe it as evidence that the binary lacks that permission. Correct and test
the verifier's exact-key extraction separately.

Verifier follow-up: replaced dotted `plutil` key-path extraction with an exact
plist dictionary check requiring boolean true for speech-recognition and
audio-input. Nine positive/negative tests pass, including missing keys, false,
string/integer impostors, nested impostors, non-dictionaries and corrupt/missing
files. Ruff passes. The same native arm64 artifact now passes the revised
verifier without the extraction warning. Full CI for the verifier change is
still required; this does not provide Developer ID/notarization acceptance.

Model-configuration implementation checkpoint: research, Realtime and input
transcription now have independently validated model IDs scoped to each provider
address. Request construction uses that selection; Realtime response validation
compares against the captured requested model rather than a global default.
No provider selection was silently changed and no generation called. Regression
tests cover provider isolation/persistence, invalid IDs, request fields and
response model mismatch. Syntax parsing passes. Native settings editing UI,
full CI and live capability testing are not yet complete for this checkpoint.

Native model-entry follow-up: the credential sheet now has a collapsed advanced
section with individually labelled research, Realtime and transcription model
IDs. Changing the address loads that provider's saved choices; corrupt stored
model configuration is shown as an error rather than silently replaced. All
model fields validate before any pending credential writes. Invalid model saves
preserve existing configuration. The voice consent sheet displays both selected
voice/transcription models and no longer promises automatic local-TTS fallback.
Whitespace/newline model IDs are rejected. Syntax/diff checks pass, while full
CI and exact-binary native model-edit/save QA remain pending. No paid request
or actual user model selection was made by this implementation.

## Exact-binary model-settings QA and discovered hang — 2026-09-06

CI [34051394664](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34051394664)
completed success for `6070dee27ad5757b329a61ebfb2000f3616a7e9c` (all jobs).
Arm64 artifact 9994687079 ZIP SHA-256 is
`ae9c0a4aae91c499f30b892d78f31240c9e6a2ff29b1774b7b7b184d868c6bc1`.
Its checksum and revised speech-entitlement verifier pass; signature remains
ad hoc, not signed/notarized release acceptance. Isolated runtime port 18768
returns healthy/schema 27.

Native model-entry acceptance did **not** pass: pressing the credentials button
left the window unresponsive. A one-second process sample of PID 79727 shows
the main thread in `presentProviderCredentials → refreshCredentialStatus →
KeychainSecretStore.contains → read → SecItemCopyMatching`, waiting in the
security service while decrypting item content. This is not proof of a bad key
or a failed runtime. No user credential or provider model selection was changed.

Follow-up replaces status-only secret reads with an exact-service/account
attributes-only query, forbids interactive authentication for this presence
check, and preserves failures as errors (not missing/configured). Actual secret
reads and save/readback validation retain their authorization behavior. Added
injected-query regression tests for no password return, no interaction, missing
items and access failures. Syntax/diff checks pass; new CI and native retest
remain required. Presence does not certify readability or Realtime support.

## Native presence and model persistence retest

Source `bcfc86ae27dd0d940378aa14467ba4b182a1b8aa`, CI `34051937128`, arm64
artifact `9994834005`; archive SHA-256
`55bd27ada55e6e3117aa6351c5b74277707ba42e4107fd6ca22eca89c52b6a70`
matches its packaged checksum. Revised release verifier succeeds (ad hoc only).
Fresh isolated native process 80632 / runtime port 18769 reports healthy/schema 27.
The previous hung isolated process and its remaining runtime were terminated;
no project data or credentials were removed.

- Credentials sheet opens and remains responsive. After state refresh the saved
  OpenAI key correctly shows stored; SD2/H3 remain unconfigured.
- Native paste/save/reopen of synthetic provider `https://nalu-model-bcfc86a.invalid/v1`
  preserves `qa-research`, `qa-voice`, `qa-transcribe` independently.
- Entering `invalid model` and pressing Save keeps the sheet open and displays
  the model-ID validation error.
- Switching back to HopsAPI restores its original three selections; Save restores
  `https://hopsapi.com/v1` as the active preference. No real model selection or key
  changed. Clipboard contents restored; no network generation or audio capture.
- Native voice-consent sheet displays HopsAPI plus the selected Realtime and
  transcription IDs. Consent is unchecked and Start disabled; cancelled without
  starting a session. The controls no longer require a decrypting presence read.
- [Native final settings screenshot](images/native-credential-presence-2026-09-06.png)
  verifies stored-key state, address and fixed Save-and-Done control. Initial AX
  snapshot before refresh was stale. An auxiliary JXA diagnostic initially used
  incorrect CFString bridging and returned -50; corrected bridging returned 0
  with both nil and non-nil results. It was not an application query defect.

Native model configuration checks pass, not whole SOP-02. Full CI completion,
live Realtime capability and same signed/notarized release-candidate acceptance
remain separate gates.

Final observation: CI 34051937128 completed success, all four jobs including
Universal. Live Realtime and signed/notarized acceptance remain unverified.
