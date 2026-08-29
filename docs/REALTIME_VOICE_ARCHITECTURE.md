# Realtime voice architecture

Status: proposed architecture; production WebRTC implementation and human QA are incomplete.

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
- [Voice activity detection](https://developers.openai.com/api/docs/guides/realtime-vad)
- [API key safety](https://developers.openai.com/api/reference/overview)
- [API data controls](https://developers.openai.com/api/docs/guides/your-data)

## Security boundary

The standard OpenAI API key remains in macOS Keychain. It must never enter SQLite,
project exports, logs, crash reports, environment variables, WebRTC events, or the
assistant conversation.

The native client must not send the long-lived key directly to the Realtime peer.
Before Mode B can ship, the bundled Runtime must have authenticated local IPC. The
native app passes the key to the trusted loopback broker only for session creation;
the broker calls `/v1/realtime/calls` and returns the SDP answer. It erases the
request buffer after use and does not persist it. A random per-launch bearer token,
file mode `0600`, origin checks, bounded request size, and endpoint allowlisting
protect that local broker. Realtime remains disabled until this boundary passes a
local-adversary review.

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

Realtime model function calls are proposals. An allowlisted local command handler
validates arguments and project state. Destructive, biometric, paid, publishing,
and script-approval actions require the same explicit confirmations as the visual
workflow. Voice must never bypass an existing product gate.

## Acceptance

- Voice-only project setup with an older adult and a guardian/child fixture.
- Slow speech, long pauses, background television, interruption, headset change,
  network loss, session expiry, and fallback to Mode A.
- Transcript/audio alignment and automatic scrolling.
- No standard API key observed in process arguments, environment, logs, SQLite,
  exports, or packet payloads after the session handshake.
- Accessibility Inspector and VoiceOver evidence from a signed release candidate.

