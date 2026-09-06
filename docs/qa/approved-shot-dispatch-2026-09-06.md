# Reviewed shot → concrete SD2 dispatch

Status: IN_PROGRESS. Mock-network integration, not real provider acceptance.

`POST /v1/production-runs/{run_id}/video-reservations/{reservation_id}/submit`
now resolves the saved reservation and its exact prepared request. It takes a
transient native provider-key header, not a replacement prompt, frame or URL.
Missing keys and browser Origin requests are rejected.

Before dispatch it verifies the reservation and price evidence, fresh quote,
current budget, decoded frame, model/compiler constraints, immutable package,
current approved script and episode, project/season identity, asset permissions,
asset digests and resolved project library. Budget/context checks repeat after
the durable intent and immediately before HTTP. The one durable submitter still
owns every paid transport invocation. Failed/ambiguous responses retain the
single-attempt marker; retry/restart returns the saved binding, not another POST.

Validation:

- Eight full local HTTP pipeline cases passed: accepted, ambiguous HTTP response,
  cancellation, newer script, changed price evidence, changed package,
  cancellation after intent but before network, and concurrent submission.
- Tests prepare a real decodable synthetic PNG, approve a synthetic script,
  construct a clearly synthetic package, observe mock official rates, reserve
  the resulting estimate, and dispatch through the real SD2 HTTP adapter with
  MockTransport. They verify exactly one or zero POSTs, restart and key redaction.
- An initial broader regression caught a second source-level paid invocation in
  the pre-submit recheck wrapper. It was replaced by a callback; the unchanged
  single-invoker test passed in the subsequent 89-test boundary/transport/pricing
  run, before the final two dispatch cases were added.
- Ruff and OpenAPI freshness passed. Full regression/CI remain to verify.

Follow-up: full runtime regression on `2bc20f64d28afb7e944b076439ff9824c38b32b9`
passed 409 tests in 51.31 seconds. Pushed
[CI 34066107435](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34066107435)
was pending at inspection; native/real-provider acceptance is still open.

No real video generation, provider charge, account lookup or publication occurred.
Native orchestration, actual AI/upstream shot planning and generated entry frames,
H3/omni, continuous task polling, final media/continuity QA and controlled release
remain open. Package fixtures do not prove a real source/story-to-video journey.
No SOP is marked PASS from this checkpoint.
