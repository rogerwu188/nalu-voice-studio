# Native video playback wiring — IN_PROGRESS

The submitted-shot panel now embeds a candidate panel for existing provider task
IDs. Opening restores local materialization receipts only (no key or provider
call). An explicit progress button queries the original task and retrieves its
completed result; pending and failed observations do not regenerate. Download
recovery first reuses local candidates, including after restart.

Playback uses AVKit with a large replay button. A private temporary MP4 is checked
against the receipt's size and SHA-256 before playback; it is not a remote signed
URL passed to the player. Leaving the view cancels its operation, pauses playback
and deletes only its temporary copy. The runtime's durable candidate remains.
Viewing is not acceptance, verified billing or publication.

Tests/evidence:

- 15 backend materialization/progress regression tests passed in 4.99s.
- Native URLProtocol coverage added for credential-free opening, pending task
  handling and error recovery without submission/key reread.
- Prior backend checkpoint 5186ad1 full CI 34086218843 succeeded. Parent native
  bridge 6614ec4 CI 34086687185 was in progress at this check.
- Local Swift package tests remain blocked by the known manifest linker mismatch.
  New native compilation/tests require GitHub macOS CI. Current installed-app
  playback, accessibility and real-media QA have NOT been performed.

Impeccable hardening guidance kept incumbent native large controls, local error
recovery and cleanup; no visual redesign or voice-engine changes.

Next: inspect native CI, verify playback in the installed app, implement bound
video acceptance and tail-frame continuation, then episode master QA/release.
No SOP is promoted to PASS by this checkpoint.
