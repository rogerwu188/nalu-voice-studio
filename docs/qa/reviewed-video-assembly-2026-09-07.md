# Reviewed opening frame to professional video preparation

Status: IN_PROGRESS; backend assembly, not paid generation or full acceptance.

Added `POST /v1/production-runs/{run}/shot-plans/{plan}/video-preparations`.
The client supplies only shot index, expected plan digest and accepted frame
review ID. It does not supply prompts, base64 files or professional JSON fields.

The service verifies the current approved plan, immutable package, episode
revision/duration and accepted shot-specific frame. It reads the materialized
image through the existing receipt/digest-bound image reader, resolves the model
profile from the production compiler, and assembles SD2 start-image transport.
The reviewed prompt is preserved. VideoPreparationService fills the reviewed
director and character scope, then runs the full existing professional gate and
atomically records the exact preparation. Current script approval is rechecked
under that lock for versioned interactive plans.

This endpoint never reads provider/model credentials or submits a provider task.
It does not authorize spending, invent a visual-QA pass, or upscale native output.
Missing director/prior-event information and required prop visual evidence fail
the existing professional gate. Continuous shots require prior accepted tail-frame
lineage; this start-image endpoint refuses to substitute a newly generated image.
Other models require their actual concrete transport, not relabeled SD2 requests.

Evidence:

- `tests/test_image_review.py`: synthetic source-to-image observation/download,
  explicit frame acceptance, full professional request preparation and durable
  replay; exact prompt/camera/frame preservation, no paid/generation approval,
  wrong index, missing director and unknown prior event rejection.
- Assembly fixture is a no-character sea shot with no props, using a synthetic
  local image. It proves transport/contract plumbing, not visual semantics, human
  character consistency, live generation or E2E production.
- Related frame/planning/paid-boundary suite: 120 tests passed in 29.23s before
  adding two further cases for changed script approval and subsequently rejected
  frame. Final six assembly cases, including both additions, passed in 3.77s.
- Ruff, OpenAPI export/backward compatibility and diff checks passed.
- Prior native handoff commit 0f8c536 full CI 34080624095 succeeded (ARM,
  Intel, Universal and Runtime). Actual native UI acceptance is still pending.

Next: native accepted-frame action into this endpoint, then actual current-price
review and protected dispatch. Prior-frame lineage for continuous shots, prop
visual evidence and remaining model transports must not be marked complete from
this start-image path. Full series/master/release objective remains unchanged.
