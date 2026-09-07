# Native edited picture-preview player — IN_PROGRESS

The episode editor now has an explicit picture-preview action and native player.
It requests the saved edit by hash from the owned local runtime, downloads into a
temporary file and verifies status, MP4 MIME/magic, size bound, exact edit hash,
actual content hash, no-audio declaration and master-denial header. The app then
checks AVFoundation playability and duration before presenting the player. No
remote provider URL, API key or autoplay is used. Playback starts on user action.

The player inherits existing native Nalu controls and text scale. Impeccable
hardening informed error preservation, stale preview invalidation and lifecycle
cleanup. Trimming/resetting invalidates old playback. Leaving cancels the download,
pauses playback and removes the private temporary preview; cancelled or obsolete
completions do not attach a player. Saved edit and originals survive errors.

Added native validator tests for exact headers/content, status, empty/changed data
and rejection of false master/audio claims. These are validator fixtures, not
playable videos. Native CI and installed-player QA remain required; the previously
reproduced local Swift manifest linker error still prevents local app validation.
No Impeccable native visual/keyboard/VoiceOver or player-compatibility PASS claimed.

The real decoder/encoder backend fixture passed again: 1 test in 4.38s, covering
the 13-second 312-frame preview and source/size/Origin/queue guards. Ruff scoped to
services/tests/scripts and diff check passed. Prior 503c6fb full CI succeeded:
https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34092538522
Parent 83a3def CI 34093298594 is running, not failed or stopped.

Still missing: current native CI and actual playback/UX evidence, explicit
edit/duration confirmation tied to the viewed version, authored audio/alignment,
final master QA and controlled release. An unvoiced proxy is not a release master.
