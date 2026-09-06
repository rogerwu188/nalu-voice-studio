# Saved image task observation

Status: IN_PROGRESS, backend/mock evidence only.

`POST /v1/production-runs/{run_id}/image-tasks/{submission_id}/refresh`
queries only a durably accepted image submission already bound to this run. A
caller cannot provide a new provider task ID. The route uses a transient native
provider-key header, refuses browser-origin calls and persists neither the key nor
provider error bodies. Query is GET only; it never calls image creation.

The service validates the local event digest, current submission, saved receipt,
request hash and provider task identity before and after query. Archive during
query and mismatched responses do not create observations. An uncertain intent
without a provider receipt cannot be converted into a fabricated query binding.
Cancellation permits read-only reconciliation of an already accepted task; it
does not restore production permission or change the cancelled run state.

Observations preserve the submission ID and exact request hash, provider status,
candidate result URLs and response digest. Identical observations are reused
after restart. Completed provider status is not image download, visual approval,
verified billing or accepted master. URL candidates containing the API secret
(including percent-decoded echo) are rejected by the shared query transport.

24 targeted image/query tests passed using MockTransport: pending, processing,
completed, failed/error, uncertain intent, query failure, wrong task identity,
archive before/during query, cancelled run, damaged receipt, secret URL echo and
restart deduplication. All image submissions in these tests use explicitly
synthetic authority; no real provider task or fee was created.

Full local regression: 479 tests passed in 68.44 seconds. Repository Ruff and
backward-compatible OpenAPI checks passed. CI for this checkpoint remains pending.

Remaining: native polling, bounded result downloads and storage, visual frame
approval, exact paid image contracts/cost approval, consecutive-shot final-frame
handoff, real video/master/release and same-candidate signed/notarized E2E QA.
