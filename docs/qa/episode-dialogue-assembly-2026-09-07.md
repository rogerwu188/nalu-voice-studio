# Episode dialogue assembly checkpoint

EpisodeDialogueService resolves every cue's current recording, listening
confirmation, transcript and caption review before building one 48 kHz stereo
PCM WAV and one episode-timed VTT. It preserves a source lineage manifest in its
return value. Missing recordings/confirmations, gaps, overlaps and incomplete
PCM coverage fail rather than padding or stretching audio. Native-local GET
`adopted-dialogue` exposes audio/captions with digest and non-master headers.

Evidence: six synthetic PCM assembly tests passed (0.45s), including exact sample
values across the join and second-cue subtitle offsets. Existing managed-media
fixture with a missing second recording is rejected (1 passed, 25 deselected,
22.28s). Ruff/diff passed and OpenAPI exported. Full two-cue service/API success,
persisted lineage/staging, cancellation, other sound layers, final mix/master,
native consumption and installed QA remain open. This is not final sound QA.

CI 34106778965 (113e2fb native caption UI) has ARM and runtime success, Intel
still running at 09:43 UTC. No full current-candidate CI PASS is claimed.
