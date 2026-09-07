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
