# Realtime voice architecture

Status: WebRTC, bounded local interview tooling, reconnect UI and credential-free CI are
implemented; credential-authorized live and human accessibility QA remain incomplete.

Nalu supports two explicit conversation modes. Neither mode replaces the other.

## Mode A — 安心按键说话

- The Mac asks one question in text and may read it aloud.
- The user presses one large microphone control, speaks, and presses again to finish.
- Apple speech recognition supplies the visible transcript.
- This remains the default and the fallback when the network, provider credential,
  consent, cost authorization, or Realtime session is unavailable.

## Mode B — 自然语音对话

- OpenAI Realtime provides native speech-to-speech conversation.
- The target model is `gpt-realtime-2.1`; pin a snapshot before release qualification.
- Use WebRTC for microphone input, model audio output, and the event data channel.
- Use semantic VAD with low eagerness for older adults so pauses and word-finding do
  not prematurely end a turn. Enable interruption so a user can speak over Nalu.
- Stream the input and output transcripts into the same auto-scrolling conversation
  view. A visible state must distinguish connecting, listening, thinking, speaking,
  interrupted, reconnecting, and unavailable.

Official references:

- [GPT-Realtime-2.1 model](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)
- [Realtime WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)
- [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [Realtime with tools](https://developers.openai.com/api/docs/guides/realtime-mcp)
- [Voice activity detection](https://developers.openai.com/api/docs/guides/realtime-vad)
- [API key safety](https://developers.openai.com/api/reference/overview)
- [API data controls](https://developers.openai.com/api/docs/guides/your-data)

## Security boundary

The standard OpenAI API key remains in macOS Keychain. It must never enter SQLite,
project exports, logs, crash reports, environment variables, WebRTC events, or the
assistant conversation.

The native Swift session broker reads the user-supplied standard key from Keychain and
uses it only over TLS to request an ephemeral client secret from
`/v1/realtime/client_secrets`. The embedded WebRTC view receives only that short-lived
secret and uses it to post its SDP offer to `/v1/realtime/calls`; the long-lived key is
never injected into JavaScript, SDP, the data channel, SQLite, environment variables,
exports or logs. The WebKit data store is non-persistent. Realtime remains fail-closed
until the key exists and the user has accepted the per-session cloud-audio/cost notice.

## Implemented native path

- A visible “自然语音对话” control opens a per-session consent sheet.
- Child projects require an additional in-person guardian confirmation.
- `gpt-realtime-2.1`, `marin`, semantic VAD with low eagerness, automatic response
  creation and interruption are encoded in a unit-tested session configuration.
- The WebRTC data channel maps listening, thinking, speaking, error and transcript
  events into the same visible conversation UI.
- A single allowlisted `record_interview_answer` function can advance the local setup
  interview after a direct answer or an explicit pause/resume/repeat/back command. A
  question, complaint or small talk is answered first without advancing the reducer.
- Tool names and exact arguments are locally validated, payloads are bounded, duplicate
  call IDs are ignored, and function output returns through the documented
  `function_call_output` → `response.create` event sequence.
- Planning approval, deletion, paid generation, biometric use and publishing are not
  exposed as Realtime tools; those actions remain behind visible product gates.
- The status strip has an indeterminate running indicator, explicit listening/thinking/
  speaking/reconnecting states, elapsed time, and a manual reconnect action after failure.
- The user chooses a 5, 10 or 20 minute session ceiling. Nalu stops microphone capture and
  the peer connection at the ceiling; choosing a new session requires a fresh consent flow.
- WebKit media capture is granted only while an explicitly consented session is
  connecting; macOS still enforces the app-level microphone permission.
- The original local push-to-talk control remains available and is disabled only while
  a live Realtime session is active.
- The Realtime prompt requires Nalu to answer an interruption first, then return to the
  unfinished interview prompt. It cannot claim that a protected local action occurred.

Still required: a credential-authorized paid connectivity/interruption/tool-call test,
provider usage/cost reconciliation, live network-loss/session-expiry recovery, packet
inspection and the full human accessibility matrix below.

## Consent, children, and cost

- Turning on Mode B must say that live audio leaves the Mac and uses a paid cloud API.
- The user may turn it off immediately; Mode A remains available.
- A child project requires guardian setup and a fresh guardian confirmation before
  the first cloud-audio session.
- Audio is not attached to feedback, telemetry, or project backups.
- Starting a Realtime session is distinct from authorizing any paid video generation.
- Show session duration and a plain-language cost estimate when reliable usage data
  is available. A spend cap must fail closed.

## Tool boundary

Realtime model function calls are proposals. The current handler exposes exactly one
bounded setup-interview function, validates its exact JSON shape and rejects every other
name. Destructive, biometric, paid, publishing, planning and script-approval actions
require the same explicit confirmations as the visual workflow. Voice must never bypass
an existing product gate.

## Acceptance

- Voice-only project setup with an older adult and a guardian/child fixture.
- Slow speech, long pauses, background television, interruption, headset change,
  network loss, session expiry, and fallback to Mode A.
- Transcript/audio alignment and automatic scrolling.
- No standard API key observed in process arguments, environment, logs, SQLite,
  exports, or packet payloads after the session handshake.
- Accessibility Inspector and VoiceOver evidence from a signed release candidate.
