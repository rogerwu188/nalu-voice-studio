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

## Capability distinction follow-up

Primary sources checked on 2026-09-06:
[OpenAI WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)
documents ephemeral-token creation and a separate Realtime calls SDP exchange.
[HopsAPI homepage](https://hopsapi.com/) shows `/v1/chat/completions`, while its
linked guide could not be retrieved unauthenticated. These sources do not establish
HopsAPI Realtime or Responses web-search support. Do not claim it is unsupported
solely from absent documentation/model IDs, or transfer OpenAI capability claims
to a compatible gateway.

Connection-check follow-up now compares all returned model IDs with each of the
provider's **saved** research/Realtime/transcription selections (not unsaved
drafts). Presence remains explicitly function-unverified; absence requests provider
confirmation rather than silently selecting a replacement or blocking by inference.
Checks use the complete sanitized list, not just ten displayed names, and do not
echo selected values that could accidentally be credentials. Three regression
tests cover independent role status, beyond-ten membership and secret redaction.
Syntax/diff checks pass; full CI and exact-artifact native result QA remain open.

## Connection-check authorization wait

On native 8af99ac process 82280 the check control stayed disabled without a model
result. A one-second process sample establishes `AIServiceConnectionCheck.check →
KeychainSecretStore.secret → read → SecItemCopyMatching` waiting in the security
service. This happens before URLSession, so its network timeout cannot bound that
wait. It is not evidence of a provider network failure or missing key.

The diagnostic now requests a noninteractive Keychain read. If authorization or
unlocking is required it returns an actionable, sanitized credential-access error
and does not contact the provider. Actual save/readback and explicitly authorized
voice operations retain their normal system authorization behavior. No permission
is bypassed. Query-policy tests cover the noninteractive diagnostic and retained
interactive policy; syntax/diff checks pass. Full CI and native denial/success
paths remain to be verified. Initial stale status display remains a separate item.

### Exact-artifact retest: the wait is still reproducible

`db83812057a9823ae5076a9a0355d795d14225be`, CI `34053223425`, arm64 artifact
`9995218616`, ZIP SHA-256
`3e172e80fc4b9448ee9ce13811a2936b7171de5b41b758a1014d8e8aa562ac73`:
archive checksum and ad-hoc signature/entitlement verification passed. Native
process 83373, existing isolated data at port 18769, displayed the saved-key badge
and HopsAPI address, but Check remained disabled. A process sample again showed
`SecItemCopyMatching` waiting before URLSession, despite the noninteractive flag.
Therefore the previous change is **not** a verified fix for the diagnostic hang.
The initial credential badge also required interaction before becoming current.
No live Realtime acceptance, paid generation, or credential modification occurred.

Follow-up adds a five-second diagnostic-only caller timeout and a shared single
worker gate. A timed-out system call cannot be forcibly cancelled; until it exits,
further saved-key diagnostic reads fail promptly without queuing more work. Its
late result cannot resume the expired request or contact the provider. A user-
entered draft remains an explicit alternative. Normal credential save and voice
authorization policies are unchanged. Tests cover success, missing value, errors,
timeout, duplicate suppression, and a late return followed by a fresh read.
Syntax and diff checks pass; compilation, CI and exact new native-artifact QA
remain required. SOP-02 stays IN_PROGRESS; no full-product completion is asserted.

### Follow-up while exact timeout artifact builds

The local runtime suite passed **312 tests** (two dependency deprecation warnings).
CI `34053223425` finished successfully for the preceding source; CI `34053634282`
is building timeout source `5a1994551e2c237a20d6b37e52959a2c65ce7ce0`, with arm64
Swift tests passed at observation time. This is not native timeout QA yet.

Credential badge arguments now use live Bindings when the sheet is constructed,
rather than pre-presentation Boolean snapshots. Native first-open verification
remains open. The diagnostic worker also releases its occupied flag before
resuming a successful caller, so an immediate subsequent check does not receive
a false busy result; the success test reuses one reader for consecutive calls.
These follow-ups require their own CI and exact-artifact native verification.

### Native timeout and duplicate-suppression evidence

Source `5a1994551e2c237a20d6b37e52959a2c65ce7ce0`, CI `34053634282`, arm64
artifact `9995343235`, ZIP SHA-256
`29a42b5d9277d0f51c1a6bacd1705e86f781684ad107a104bef5f4f73c2447d8`.
Checksum matched its manifest; ad-hoc signature and speech entitlements passed.
Native process 84742 reused the isolated QA database at port 18769.

- macOS SecurityAgent independently displayed a Nalu Keychain access request
  requiring the login Keychain password. No password was read, entered or approved.
- First Check: after a seven-second observation delay (7.348s including AX calls),
  the sheet displayed the credential timeout message and Check was enabled.
  This observation proves return by that point, not an exact five-second UI SLA.
- Second Check: after a half-second observation delay (0.714s including AX calls),
  the sheet displayed the previous-read-pending message and Check remained enabled.
- [Native screenshot](images/native-keychain-timeout-2026-09-06.png) shows the
  HopsAPI address, saved-key badge, pending message and enabled Check control.
- No provider response or real voice session was obtained. The control-flow
  error occurs before networking; no paid generation or credential changes occurred.
- This artifact still exhibits the initial stale badge; the later Binding change
  in `ab3283d` is not included and needs a separate first-open native check.

This closes only the bounded timeout UI observation, not SOP-02 or the product.

### First-open Binding artifact: native check remains open

Source `680256be3c25c6fee7ea667e257dfa499d858a47`, CI `34054002146`, arm64
artifact `9995431149`, ZIP SHA-256
`3460c80c87a41c8d49628d6fbfb91998e02a53ec2dca6810f89ee79da1842f61`:
checksum and ad-hoc signature/entitlements passed. Isolated native process 85349
and Runtime listener 85365 started using the existing QA data/port 18769.
CoreGraphics window 5587 and its screenshot show the main window and online
Runtime. However System Events returned an empty windows list for this exact
process even after startup. Opening the credentials sheet through the recorded AX
path therefore failed with invalid index. This is **not** first-open badge PASS,
and the cause of the AX discrepancy is not established. No security authorization
was approved or modified. Retry native first-open verification when controls are
accessible; do not treat the prior artifact's badge as this artifact's evidence.

The main-window screenshot also exposes a separate misleading status: a local
dry-run preflight fixture says “Nalu 正在工作，没有停”. Inspect progress status
semantics before claiming that preflight means an active production worker.
