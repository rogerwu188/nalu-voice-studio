# Per-shot estimate approval and reservation

Status: IN_PROGRESS. Local transactional estimate control, not provider billing verification.

`POST /v1/production-runs/{run_id}/video-task-preparations/{preparation_id}/estimate-approvals`
binds an explicit confirmation to the saved preparation digest, request digest,
package digest, task key and run estimate. Its SQLite `BEGIN IMMEDIATE`
transaction checks all existing shot reservations before appending a durable
`video_estimate_reserved` event. Existing preparations remain unchanged.

Repeated same-shot/same-estimate approvals return the original reservation;
different request or estimate cannot silently replace it. Newer preparations,
dry runs, cancelled runs, archived projects, invalid prior reservations and
provider tasks without cost reservations are rejected. Child projects require
guardian approval. Ambiguous/failed tasks do not automatically release capacity.

Tests: 63 paid-boundary tests passed, including concurrency (60 already reserved
out of 100; only one of two concurrent 40-credit requests succeeds), duplicate
approval, restart, changed budget/digest/amount, strict integer validation,
archived/cancelled/dry-run/child guards, stale preparations and corrupt prior
reservation. Ruff passed and OpenAPI regenerated. Tests use synthetic local
records only; no provider calls or charges.

Important limits: these are caller-reviewed **estimates**, not independently
verified provider quotes or guarantees that a provider cannot overcharge. Each
receipt says `provider_price_verified=false`,
`provider_charge_cap_guaranteed=false`, `generation_performed=false`. This
endpoint does not dispatch paid work. Actual quote validation, authorization
revalidation immediately before dispatch, budget/reconciliation policy for
imported projects, native confirmation, AI/upstream shot planning and the real
video/master/release path remain open. No SOP becomes PASS from these tests.
