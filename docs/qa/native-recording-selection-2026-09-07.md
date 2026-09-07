# Native recording selection state — IN_PROGRESS

EpisodeAudioModel reads the production run and project assets without writes,
filters recordings to active consent and matching episode/season scope, and uses
the saved asset SHA rather than asking users for IDs. It prepares a plain-language
readback naming the recording, cue, offset and duration before explicit attach.
The backend remains the authority for consent records, guardian use and bytes.

Uncertain attachment retains its exact pending request and disallows replacing or
cancelling it. Successful retry records the returned take and does not claim
listening, voice cloning, speech alignment, final audio approval or release.
Read failures preserve original files and pending state. This is model logic;
visible selection/audition controls and persisted take recovery are still required.

Native tests added for run/asset loading, out-of-episode and unauthorized filtering,
no POST during selection/readback, 503 retention and retry completion. They still
require current native CI. Backend synthetic recording regression passed again
(1 test, 8.94s); scoped Ruff and diff passed. Parent e72c1f4 CI 34097214521 is still
in progress. Installed app and actual accessibility/playback QA remain unchanged.

Next: connect the cue/recording choice and actual audition controls, then take
confirmation, speech-based subtitles and authored final audio/master/release.

## Visible selection and audition checkpoint

EpisodeAudioPanel is now attached below successful approved sound preparation.
Each cue shows its narration and duration, an authorized-recording picker, text
readback, audition and explicit attachment readback/confirmation. Uncertain
attachment exposes same-request retry and prevents replacing the selected asset.
Empty/error states direct users to existing import/authorization or refresh.

Audition reads only a bounded local regular file, rejects symlink resolution
changes, verifies SHA bytes off the main thread and asks AVAudioPlayer to play the
cue-length segment from the recording start. It stops on switching, readback,
attachment, explicit stop or disappearance, and tracks end/error status. This is
source audition, not synchronized picture playback or final voice approval.
Nonzero source-offset selection and persisted take recovery remain unfinished.

Impeccable hardening preserved Nalu typography, native large controls and wrapping
status text. Added native byte-validation tests cover exact bytes, remote URI,
missing consent and modified file rejection; the bytes are not real audio, and
the test does not claim playback QA. Current native CI is required. Parent
7b8a0be CI 34097684986 ARM/Intel/Runtime were still running at inspection.
Backend synthetic audio attachment regression passed (1 test, 8.88s), scoped
Ruff/diff passed. No current installed screenshot, VoiceOver, actual speakers,
end-to-end family narration or final audio QA has been obtained.

Next: recover recorded takes after restart and add explicit listened-to decisions,
then speech-based subtitle alignment, authored final audio and master/release QA.
