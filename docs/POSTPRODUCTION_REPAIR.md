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

## Local semantic dialogue and authored-boundary gate

The Qingshan workspace task now declares one required `shot_manifest` output and writes
an episode-specific `nalu.shot-boundary-output-contract/v1` file. The finished manifest
must bind the immutable production-package digest, list every authored unit on the final
master timeline, carry a canonical manifest digest and bind each incoming transition to
its own digest-checked contract. The contract records transition type, whether visible
change is required and the intended audio bridge; it is production output evidence, not
a value reconstructed later from the rendered video.

During `qa_review`, the native macOS application downloads the exact sealed master and
verifies its `X-Nalu-Master-SHA256` before use. It asks Apple's `zh-CN` speech recognizer
to set `requiresOnDeviceRecognition`; if on-device recognition is unavailable, Nalu stops
instead of silently sending the master to a cloud recognizer. The transcript and timed
segments are submitted with the sealed-master digest and the fixed recognizer identity.

`POST /v1/production-runs/{run_id}/semantic-media-qa` requires the structure and decoded
reports to have passed against the same seal. It compares normalized visible WebVTT text
with the local transcript at a minimum 80 percent recall, validates segment order and
duration, and decodes the frames immediately before and after every authored boundary.
Missing sides, large frame gaps, black frames, an expected-but-absent visual change,
invalid transition contracts, package drift and recognizer/locale drift fail closed.
The immutable report creates `semantic_asr` and/or `shot_boundary` repair tasks and is
required by both production completion and offline release packaging.

This is automated release-blocking evidence only. It does not claim lip-sync quality,
editorial taste, identity continuity or completion of the required original-resolution
human audiovisual review.

## Selected-shot, normalization, stem and published-mix lineage gate

The Qingshan task also declares an episode-specific
`nalu.postproduction-lineage-output-contract/v1`. Its resulting sealed manifest binds the
immutable production package, final master and captions. Each selected shot must carry
an `ADMITTED_FOR_ASSEMBLY` decision, provider task and receipt digest, original source
file digest, normalized segment digest and contiguous source/final timeline coordinates.

`POST /v1/production-runs/{run_id}/postproduction-lineage-qa` resolves files only inside
the run's export directory and rejects symlinks or path traversal. It decodes each
normalized segment instead of trusting declared metadata, checking target dimensions,
frame rate, `yuv420p`, zero-based picture/audio timestamps, 48 kHz stereo audio and
duration. Dialogue, ambience, foley, music and SFX must each be explicitly included or
creatively omitted; dialogue cannot be omitted, included stems must be non-silent decoded
48 kHz stereo files, and every included stem must bind one or more cue digests.

The published mix is decoded, fingerprinted and checked for clipping, duration and 48 kHz
stereo format. Its decoded energy envelope must match the exact sealed master's audio at
or above the fixed threshold. The subtitle record must resolve to the exact sealed WebVTT
file and bind its source contract. The immutable result is required by completion and
offline release packaging on the same output seal. Failures produce specific
`shot_selection`, `media_normalization`, `audio_stems`, `published_mix` or
`subtitle_lineage` repair tasks and do not advance the run.

This gate proves artifact selection and technical lineage. It does not prove that the
creative mix is tasteful, that dialogue is intelligible in a noisy room, or that picture,
identity and continuity are acceptable to a human reviewer.
