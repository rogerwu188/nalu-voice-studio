# Actual adopted-dialogue render fixture

The new video_assemble_stage_render regression drives two adopted video shots,
listening-confirmed recordings, corrected captions, whole-episode assembly,
durable staging, mix preparation and the real postproduction HTTP endpoint.
It creates a 13-second 64x64 render using actual encoded synthetic video/PCM,
four explicitly supplied synthetic tone layers, and exact staged VTT. The real
materializer's decoded-lineage/loudness checks pass and the run enters QA_REVIEW.
The fixture explicitly seeds running/postproduction state and a synthetic
workspace manifest: it does not demonstrate production authorization or install.

This test exposed and fixed two integration defects:
- Saved accepted video reads inherited the new-shot preparation status gate.
  Internal saved-read validation now permits running/QA only for the current
  run; preparation/submission paths retain their original status restrictions.
- Source-video QA incorrectly required an audio stream even though separate
  dialogue/stems supply audio. Only source-picture checks may omit audio;
  normalized segments and final masters still require decoded audio.

Initial fixture failures included duplicate run insertion and insufficient
synthetic tone loudness. State setup and tone amplitude were corrected; release
loudness limits were NOT relaxed.

Evidence: full render 1 passed, 26 deselected (54.66s). Five focused state/audio
requirement tests passed (0.31s). Ruff/diff passed. Actual local rendering of
synthetic fixtures is not real user/provider QA, subjective audio quality,
signed/notarized installation or controlled release acceptance. Current CI
still needs verification. No SOP upgraded to PASS.

Next: verify replay/cancellation and source-change handling around actual render;
connect native sound selection and production action; then content/semantic QA,
master review and controlled release.

Replay follow-up: the actual render fixture now reopens the HTTP client and
replays materialization in QA_REVIEW. It gets the identical result, unchanged
master bytes and no new run events. Revoking the source recording's consent
then refuses replay without overwriting the existing master or adding events.
Result: 1 passed, 26 deselected in 66.28s. Audio decoder midstream cancellation
also raises rather than yielding a completed decode (1 passed, 2 deselected,
0.51s). This cancellation test is decoder-level, not whole-application QA.
Ruff/diff passed. CI 34109001146 remained running at 10:09 UTC.

Open gap: consent validation must extend beyond materialization replay to seal,
master access and release for the exact adopted-source lineage. Full render
cancellation/cleanup, native action and final acceptance remain unverified.
