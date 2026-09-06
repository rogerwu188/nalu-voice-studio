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
