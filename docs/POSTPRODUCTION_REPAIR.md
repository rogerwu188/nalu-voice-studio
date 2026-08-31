# Release-blocking postproduction repair plans

A failed release gate does not become a generic error or disappear after restart. During
production completion, Nalu verifies the sealed package, workspace, master, captions and
structured human QA evidence. Any failure keeps the run in `qa_review` and writes a
digest-bound `postproduction-repair-plan.json` beside the immutable production package.

Repair plans contain one or more release-blocking tasks for:

- missing or changed sealed outputs;
- missing master, captions or final QA evidence;
- malformed QA evidence or evidence bound to another run/master;
- missing or failed decoded picture/audio/caption-alignment evidence;
- incomplete original-resolution review;
- failed picture/identity/wardrobe/space/pose/prop checks;
- failed dialogue, ambience, foley, music or audio synchronization;
- failed caption text/timing/readability;
- failed cross-shot or cross-episode continuity; and
- failed safety, consent, rights or release review.

Each task states the affected target, the issue and the action required before a new
release candidate can be sealed. The repair plan and ordered run event are idempotent for
the same sealed evidence, so repeatedly asking to complete does not create duplicate work.
`GET /v1/production-runs/{run_id}/postproduction-repair-plan` returns the persisted plan
after restart and verifies its SHA-256 before returning it.

Because rendered outputs are immutable once sealed, a repair never edits the old master
or QA report in place. It creates a repair run, produces new outputs and repeats sealing
and release-blocking review. This contract does not turn an automated decoder result
into semantic ASR or human audiovisual acceptance; those gates still require their own
evidence.

## Container and caption timeline gate

`POST /v1/production-runs/{run_id}/media-structure-qa` performs a deterministic local
gate against the sealed files. It verifies ISO-BMFF box boundaries, `ftyp`, `moov`,
`mdat`, fast-start ordering and a valid positive movie-header timescale/duration. It also
parses UTF-8 WebVTT cues, rejects invalid or reversed timestamps, overlap/out-of-order
cues, empty timelines and cues extending beyond the master duration. The digest-bound
report is idempotent for the same seal. A failure produces `mp4_structure` and/or
`caption_timeline` repair tasks.

These are structural golden-fixture checks. They do not decode picture or audio and must
not be reported as frame-repeat, ASR/VAD, synchronization or human visual acceptance.

## Decoded picture, audio and cue-alignment gate

`POST /v1/production-runs/{run_id}/decoded-media-qa` opens the exact sealed master with
PyAV/FFmpeg, decodes every picture frame and a normalized 16 kHz mono audio stream, and
writes a digest-bound `decoded-media-qa.json`. The picture gate rejects missing or
undecodable streams, changing/odd dimensions, non-monotonic or gapped timestamps,
excessive identical-frame runs and prolonged black runs. The audio gate rejects missing
or undecodable samples, insufficient voice activity, prolonged silence and excessive
clipping. A cue-alignment gate verifies that at least 80 percent of valid WebVTT cues
overlap a decoded voiced interval.

The report is deterministic and idempotent for the same output seal. Failure generates
specific `decoded_video`, `frame_repeat`, `audio_vad` and/or
`caption_speech_alignment` repair tasks. Production completion and offline release
packaging both fail closed unless the structure and decoded reports are present, PASS,
and bound to the exact current seal. Playable AAC/MP4 golden fixtures cover both a pass
case and a frozen-picture/silent-audio failure case.

The report explicitly stores `semantic_asr_verified: false`. Voice activity and cue
overlap are not transcript correctness, lip sync, shot-aware transition continuity or a
human viewing claim.
