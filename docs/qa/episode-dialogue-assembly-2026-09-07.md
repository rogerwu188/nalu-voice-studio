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

Full service/API follow-up: the synthetic managed-media workflow now attaches
and adopts both recordings, saves/explicitly confirms both transcripts, then
exports a 13-second WAV and episode VTT through reopened HTTP clients. Both PCM
regions are compared sample-for-sample to accepted source exports. The second
cue starts at 7 seconds. Missing captions, superseded transcript and withdrawn
listening confirmation fail. Exports append no events. Audio/caption responses
carry the same source-lineage digest; an optional expected-lineage query rejects
mixed-version downloads (separate mocked transport boundary test).

Combined result: 8 passed, 25 deselected in 47.08s; Ruff/diff passed; OpenAPI
updated. This is actual processing of synthetic fixtures, not provider/family QA.
CI 34106778965 on 113e2fb is now fully successful, including Universal. Current
checkpoint CI is pending. Persisted staged inputs and remaining sound layers
must still be wired into ProductionService.materialize_postproduction; no final
mix, signed installed app or release is declared complete.
