# Concrete video request preparation

Status: IN_PROGRESS; no paid or native end-to-end acceptance.

`POST /v1/production-runs/{run_id}/video-task-preparations` now accepts a
professional shot request and persists the exact request plus its opening image
in a `video_task_prepared` run event. This is a production-adapter interface,
not a form for the story author to fill out.

Before saving, the runtime verifies the production package digest, model and
complete QingShan paid-boundary contract. The SD2 projection preserves prompt,
duration and native resolution, rejects extra references, and binds the image
bytes to the opening-anchor digest. PyAV decodes a bounded PNG/JPEG and checks
its dimensions against the selected aspect ratio. Decoding is not semantic or
artistic QA: `visual_semantics_verified` remains false.

Each record contains request/package/preparation hashes and decodable frame
dimensions. Repeat requests deduplicate; SQLite restart retains the record.
The record explicitly says `paid_approved=false` and `generation_performed=false`.
Cancelled/other ineligible runs and archived projects cannot prepare new shots.

Validation: 67 paid-boundary and SD2 tests passed; seven preparation cases cover
valid decoded PNG, garbage bytes, changed anchor hash, extra reference, wrong
package binding, cancellation and ratio mismatch. Valid cases check exact saved
payload, duplicate calls, no remote task creation and restart. Ruff passed;
OpenAPI regenerated. No real family media or provider credentials used.

Full regression on `cab966fae03e8c3dad214a0b1492b88a12e18caa`: 385 passed in
51.72 seconds; OpenAPI freshness check passed. GitHub
[CI 34065405217](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34065405217)
was pending at inspection; native QA and current-candidate CI are not yet proven.

Remaining: actual AI/upstream shot-plan and generated first-frame inputs; budget
review/reservation; approval tied to this exact saved record; concrete transport
dispatch; native orchestration, media retrieval/QA, billing and release. This
does not make either full user journey or SOP-04/08 complete.
