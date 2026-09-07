# Bound video retrieval and local candidate storage

Checkpoint only. No real provider media, billing acceptance, native playback,
creative approval or finished episode/master is claimed.

## Implemented

`video_download.py` retrieves only public HTTPS destinations with DNS validation
and pinned public IP/TLS hostname verification on every redirect. Requests carry
no provider credentials. Transfer size (128 MB), deadline, redirects, encoding,
MIME type and Content-Length are bounded/checked. MP4 bytes must decode into a
single H264/HEVC/AV1 short video with bounded geometry, frames, pixels and timeline.
The MP4 reader disables external data references and restricts protocols. Audio
and visual semantics are explicitly **not** accepted by basic decode validation.

`POST /v1/production-runs/{run_id}/video-observations/{observation_id}/materialize`
requires an intact completed provider observation and existing matching Giggle
SD2 binding/task ID. It saves a hash-named, owner-only immutable MP4 under the same
run. It preserves task/request/observation lineage and hashes the source URL rather
than copying it into the materialization receipt.

After download it revalidates context under one SQLite writer lock, then publishes
the immutable file and receipt. Concurrent writers converge on one receipt. On
restart an existing receipt validates the saved bytes and is reused without a
download or generation. Missing/corrupt files require reconciliation, not regeneration.
Source task state and billing records are not changed by retrieving a candidate.

`GET /v1/production-runs/{run_id}/video-results/{materialization_id}/content` returns
the verified local candidate with no-store/nosniff. Browser-origin materialization
and preview are rejected. The service does not yet support other provider models;
it does not relabel H3 results as SD2.

## Tests

- 24 download/materialization tests passed initially in 4.05s, using actual encoded
  synthetic MP4 bytes, mocked transport and synthetic bound observations.
- Public redirect validation, no auth headers, wrong MIME/encoding, truncation,
  oversize/decoder budgets, duration and invalid media.
- Completed vs pending/wrong-task observations, archived context (including during
  download), concurrent/restart idempotence, owner-only files, immutable corruption
  detection, native-only endpoint access, no master/creative/billing auto-approval.
- Ruff and OpenAPI regeneration passed. Current code requires full CI acceptance.
- Final regression including video retrieval, existing image retrieval, paid
  submitter boundaries and progress audit: **127 passed in 37.30s**; diff clean.
- Prior native generation panel `055cb1f` full CI
  [34085540428](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34085540428)
  passed ARM, Intel, Universal and runtime jobs; not real E2E acceptance.

## Remaining

Connect provider status refresh and materialization to native playback/review;
bind accepted frame lineage into the next continuous shot; validate durations,
visual/audio content, episode edit/master and controlled release. Current retrieval
supports short MP4 candidates up to 30 seconds and is not a long-film import path.
No full SOP is promoted to PASS.
