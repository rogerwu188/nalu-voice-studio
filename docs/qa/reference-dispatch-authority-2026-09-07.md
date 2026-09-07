# Reference-specific dispatch integration

Status: IN_PROGRESS. This joins local source/budget authority to the durable image
submitter, but is **not** an activated paid endpoint or real generation evidence.

`ReferenceDispatchService` binds one image estimate reservation to its exact
reference preparation, confirmed design, current script/plan and production
package. Keyframe reservations cannot enter this reference-only path. The
existing preparation compiler matches the pinned QingShan asset factory; its
reference path does not require invented shot-only spatial/action PASS records.

Before intent creation and again before HTTP, the service revalidates current
inputs, project/run eligibility, guardian spending approval and the shared
image/video budget ledger. Validation inside the SQLite intent transaction is
read-only; it does not start a nested writer transaction. Existing accepted or
uncertain outcomes are returned without another key read, price check or POST,
even if the run was subsequently cancelled. Changed bindings fail closed.

Price verification remains a required **runtime-owned, local read-only callback**
with no default implementation. No HTTP caller can provide it; no route has been
exposed. Its production implementation must verify the applicable price evidence
and exact spending approval. The public image price is still unavailable; this
checkpoint must not be used as an excuse to submit with a synthetic verifier.

Nine mock-network cases passed in 5.47s: success, unavailable price, changed plan,
cancelled run, missing child guardian approval, reduced budget, wrong purpose,
ambiguous response and price invalidation immediately before HTTP. They exercise
real repository/preparation/reservation/submission code but inject synthetic
price acceptance and provider receipts. No real external call or charge occurred.
Full regression: 577 passed in 179.23s; Ruff, diff and progress-schema checks
passed. The preceding native progress candidate `1dd7962` completed all four CI
jobs in [34072916544](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34072916544).
This new dispatch code still awaits its own CI and real-production acceptance.

Next: complete production price verification and the explicit native spending
handoff, then exercise actual reference generation and review; independently
complete full keyframe compilation and sequential video/master/release. The Mac
unlock and Hops authorization blockers do not remove these implementation tasks.
