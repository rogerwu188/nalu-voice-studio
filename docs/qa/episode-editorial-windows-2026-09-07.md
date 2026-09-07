# Adopted-video editorial windows — IN_PROGRESS

POST `production-runs/{run_id}/episode-edit-drafts` accepts the exact staged input
hash and ordered per-shot source windows. The shared staging service revalidates
current adoption, source bytes and production lineage under one writer lock.
It rejects archived projects, stale inputs, missing/reordered/duplicate cuts,
out-of-source ranges, subframe cuts and whole-source passthrough. Source duration
comes from decoded media, not the shot's planned duration. Browser Origins reject.

The draft emits existing typed postproduction sources, 24 fps frame counts and a
contiguous edited timeline. Original media is unchanged. Planned and edited
durations remain separate; edit approval, caption retiming, audio and master QA
are NOT inferred. Replay verifies source files before returning the same event.
Inputs now include decoded source duration; older input hashes must be refreshed.

Nine focused regressions passed in 11.43s, including a two-shot synthetic media
test and the existing full-provider passthrough rejection. The edited 8+7 second
sources produce a 7+6 second timeline; the actual materializer's frame decoder
successfully reads all 168+144 selected output frames. Tests cover invalid ranges,
exact hash binding, order, restart, corrupt staged media and unchanged originals.
Ruff passed for services/tests/scripts; OpenAPI regenerated.
The complete image-review, video-materialization and video-download regression
set subsequently passed: 50 tests in 16.15s. OpenAPI check and diff check passed.

Still missing: native plain-language edit controls/preview/confirmation, approved
timing changes and corresponding sound/caption retiming, verified workspace and
receipt handoff, authored audio, complete real rendered master QA and release.
This does not claim a real production E2E or completed SOP. Parent c6881bd CI
34091013930 was still in progress at this checkpoint.
