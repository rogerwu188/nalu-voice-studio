# Release-blocking postproduction repair plans

A failed release gate does not become a generic error or disappear after restart. During
production completion, Nalu verifies the sealed package, workspace, master, captions and
structured human QA evidence. Any failure keeps the run in `qa_review` and writes a
digest-bound `postproduction-repair-plan.json` beside the immutable production package.

Repair plans contain one or more release-blocking tasks for:

- missing or changed sealed outputs;
- missing master, captions or final QA evidence;
- malformed QA evidence or evidence bound to another run/master;
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
and release-blocking review. This contract does not by itself claim that ASR/VAD, media
boundary, frame-repeat or human audiovisual QA has run; those gates still require their
own evidence.

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
