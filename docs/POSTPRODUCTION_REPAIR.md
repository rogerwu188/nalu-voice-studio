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

## Runtime-owned postproduction execution

Qingshan provider results are staged under the run's managed
`exports/provider-results` directory. The episode task carries
`nalu.postproduction-materialization-contract/v1`; every selected source interval must
bind the provider task ID, receipt SHA-256 and exact local source-file SHA-256. Dialogue,
ambience, foley, music and SFX must each supply exactly one non-silent source with cue
provenance. The captions source and subtitle contract are digest-bound as well.

`POST /v1/production-runs/{run_id}/postproduction-materializations` is a local execution
endpoint, not a provider submission endpoint. It rechecks every source path and digest,
decodes and trims selected frames, normalizes each segment to the requested even-sized
`yuv420p` frame and fixed frame rate, resets picture/audio timestamps, and writes 48 kHz
stereo audio. It normalizes all five audio layers, applies their explicit gains, renders
a non-clipping published mix, assembles the selected segments in order and encodes that
same mix into the final MP4. The copied WebVTT and an execution-derived
`nalu.postproduction-lineage-manifest/v1` are emitted with the master.

Audio decoding, normalization, five-layer mixing and final-master audio encoding use
fixed 8,192-sample stereo chunks. The Runtime never retains a whole source, stem, mix or
episode-length floating-point accumulator in Python memory. Every stem is normalized to
an intermediate digest-bound WAV; the mixer then reopens the five stems in aligned
chunks, applies gain and clipping protection with a fixed-size NumPy vector per chunk,
writes the published mix, and streams that file into the final MP4 encoder. Automated
fixtures consume the entire source while asserting the fixed chunk ceiling, a Python
heap peak below 4 MiB and numerical equivalence with the original scalar five-stem mix.
The release QA harness can additionally materialize the full allowed 1,800-second
timeline through the bundled Runtime while sampling the complete PyInstaller process
tree RSS, allocated disk, free disk and throughput. It rejects a result above the
explicit RSS ceiling or below the explicit realtime factor; source-code heap tests are
not substituted for that device evidence.

All outputs and the immutable result record are built in a private staging directory and
renamed together into `exports/materialized/{plan_sha256}`. Sources are rehashed after
rendering and the existing lineage inspector decodes the finalized outputs before the
run can enter `qa_review`. If the process stops after the directory commit but before the
SQLite state transaction, replaying the identical request verifies and adopts the same
result. A changed plan, a changed source, multiple finalized results, artifact drift or
an existing output seal fails closed. The run and episode enter `qa_review` with one
ordered event and one episode transition in the same SQLite transaction.

One filesystem lock serializes materialization for a run workspace across Runtime
threads and process restarts. After the owning process dies, the next lock holder removes
only private `.nalu-postproduction-*` stages abandoned under that exact export root;
symlink or non-directory lookalikes fail closed. A live cancellation is polled from
SQLite at a bounded interval throughout frame selection, audio decoding, stem/mix writes
and final encoding. Cancellation aborts the generators and removes the private stage
without recording a materialization event. Resume revalidates the existing Qingshan
workspace instead of rebuilding it, so already downloaded digest-bound provider results
survive. The exact retry then completes once and records one event; it never silently
restarts a paid provider call.

The executor performs no network call and grants no paid authority. It executes an
already-reviewed edit/mix plan; it does not decide which creative take is best, prove
speech intelligibility or replace final human review.

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

## Production-bound visual continuity gate

The Qingshan workspace now also declares
`nalu.visual-continuity-output-contract/v1`. Its sealed manifest is bound to the
production package, final master and confirmed project-library snapshot. It must declare
one local analyzer identity, version and model digest, retain all five required domains
(`identity`, `wardrobe`, `space_axis`, `pose` and `props`), and attach every observation
to a decoded evidence-frame SHA from the authored shot interval.

The workspace also emits immutable `nalu.visual-analyzer-inputs/v1` before production.
It resolves each consented local character photo or prop reference to one confirmed
library entity by its stable name or confirmed alias, and binds the asset ID, managed
local URI, content digest, consent scope and entity revision. Character rows carry the
confirmed identity, wardrobe, space/axis, pose and held-prop targets. Missing characters,
references, digests or explicit targets leave the contract `BLOCKED`; they are never
filled with guessed defaults. The contract is local-only, forbids provider upload and
requires both asset rehashing and final-master frame digests. Consent statements are not
copied into the analysis workspace. `READY` means only that inputs are complete enough
for a local analyzer; it is not evidence that perceptual analysis ran or passed.

After Runtime-owned postproduction has materialized one final master,
`POST /v1/production-runs/{run_id}/local-visual-analysis` rehashes every confirmed
reference, decodes the midpoint frame for every authored shot and invokes the packaged
`NaluVisualAnalyzer` executable. That helper uses Apple Vision feature prints for
character/prop similarity, Core Image area-average color for wardrobe evidence, and
Vision body-pose/face/saliency observations for pose and screen-axis evidence. It has no
network transport, receives only managed local paths, and returns measurements rather
than caller-selected PASS flags. Runtime binds those measurements to the analyzer binary
SHA-256, exact frame SHA-256, production package and confirmed entity revision, then
writes one immutable manifest and one idempotent run event. A restart between the file
commit and SQLite event commit replays the same evidence without running Vision twice.

This is deliberately a conservative baseline. Whole-frame feature-print similarity can
fail when a character or prop occupies a small part of a complex shot; area-average color
does not segment a garment; and body pose can be unknown when joints are occluded. Such
uncertainty becomes a domain failure and repair task. It is never replaced with a guessed
observation, and it does not replace original-resolution human audiovisual review.

`POST /v1/production-runs/{run_id}/visual-continuity-qa` does not trust the manifest's
PASS flags. It reopens the exact sealed master with PyAV/FFmpeg, decodes the cited frame,
recomputes its grayscale pixel SHA-256 and then calculates every observation's result
from the expected/observed value and a fixed per-domain confidence floor. Identity and
wardrobe checks must reference the exact confirmed character revision frozen into the
production package; a prop reference, when present, must bind the exact confirmed prop
revision. Missing domains, stale authority, a lowered confidence, a fabricated frame,
package/library drift or a declared/computed status disagreement fail closed.

The resulting `nalu.visual-continuity-qa/v1` report is immutable, digest-bound and
required on the same output seal before production completion or offline release
packaging. Failures create one or more `visual_continuity_manifest`, `visual_identity`,
`visual_wardrobe`, `visual_space_axis`, `visual_pose` and `visual_prop` repair tasks.
Golden fixtures cover a five-domain decoded pass, wardrobe mismatch and a frame SHA that
does not belong to the master.

This gate verifies local analyzer lineage and objective contract consistency. It does
not establish that the analyzer is perceptually correct, replace original-resolution
human review, or turn a test-double analyzer into production model evidence.
