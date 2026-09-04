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
- The target model is `gpt-realtime-2.1`. The current official model page does not expose
  a distinct dated snapshot identifier, so release qualification must re-audit this alias
  and pin a documented snapshot if OpenAI publishes one.
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
Before any secret reaches WebKit, the broker requires the official response envelope to
contain an exact `realtime` / `gpt-realtime-2.1` session, an unmodified value no larger
than 4,096 UTF-8 bytes, and at least five seconds of remaining lifetime. Missing,
expired, wrong-session, wrong-model, padded, oversized and malformed responses are
rejected locally. This validation does not replace the still-required credential-
authorized live-session and packet-boundary QA.

## Implemented native path

- A visible “自然语音对话” control opens a per-session consent sheet.
- Child projects require an additional in-person guardian confirmation.
- `gpt-realtime-2.1`, `marin`, semantic VAD with low eagerness, automatic response
  creation and interruption are encoded in a unit-tested session configuration.
- The WebRTC data channel maps listening, thinking, speaking, error and transcript
  events into the same visible conversation UI. The embedded page rejects non-text,
  malformed, missing-type and oversized messages before mapping them. Its native bridge
  accepts only exact `kind` / `value` status, transcript and error envelopes with bounded
  values; the tool envelope has its own exact schema. This shared contract also ensures
  completed user and assistant transcripts reach the visible conversation.
- A single allowlisted `record_interview_answer` function can advance the local setup
  interview, save reversible season/episode/script revisions, and apply explicit
  pause/resume/repeat/back commands. A question, complaint or small talk is answered
  first without advancing the reducer.
- When a Realtime session is already active, the visible “用语音讲…” controls reuse that
  WebRTC microphone instead of opening Apple speech capture concurrently. Nalu cancels
  an unfinished answer before reading the newly selected planning question.
- Season and script approval can pass through the same function only after the user has
  visibly armed that exact approval task, the reducer hears an exact positive phrase,
  and the child guardian gate passes. The approval audit records `voice_realtime`.
- Tool names and exact arguments are locally validated, payloads are bounded, duplicate
  call IDs are ignored, and function output returns through the documented
  `function_call_output` → `response.create` event sequence.
- Unarmed approval, deletion, paid generation, biometric consent/use and publishing are
  not exposed as Realtime operations; those actions remain behind product gates.
- The status strip has an indeterminate running indicator, explicit listening/thinking/
  speaking/reconnecting states, elapsed time, and a manual reconnect action after failure.
- Peer failure, a sustained disconnected state, provider errors and data-channel close or
  error use one failure gate, so capture is stopped and only one retry notice is shown.
  Intentional stop does not surface a false network error, and delayed callbacks from an
  older channel cannot fail its replacement.
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
bounded conversation-flow function, validates its exact JSON shape and rejects every
other name. A season/script approval is accepted only while its native approval reducer
is explicitly armed and its existing guardian and exact-language checks pass. Destructive,
biometric-consent, paid and publishing actions are not callable. Voice must never bypass
an existing product gate.

## Acceptance

- Voice-only project setup with an older adult and a guardian/child fixture.
- Slow speech, long pauses, background television, interruption, headset change,
  network loss, session expiry, and fallback to Mode A.
- Transcript/audio alignment and automatic scrolling.
- No standard API key observed in process arguments, environment, logs, SQLite,
  exports, or packet payloads after the session handshake.
- Accessibility Inspector and VoiceOver evidence from a signed release candidate.
