# Repair creative draft recovery — incomplete production flow

POST `/v1/production-runs/{run_id}/repair-shot-draft` accepts source run/event/plan
digest and target package digest. It checks explicit immutable repair lineage,
current source repair plan/seal, same episode/project/season, original approved
creative plan integrity, unchanged approved script and duration. It carries only
creative content into a new unapproved draft. New tasks await review and frames;
provider identities, spending and prior approval are not copied.

The transaction rejects existing target downstream work and provider tasks. Exact
restart replay returns the current identical draft; subsequent creative edits
prevent overwriting. Browser Origin calls are rejected. No model/network call.

Three repair integration cases pass4.28s; new assertions cover source hash mismatch,
Origin rejection, false approval/generation/spending flags, task reset, Runtime
restart replay and no overwrite after revision. Synthetic original plan fixture.
OpenAPI regenerated; native caller, real asset reuse and repaired master still
need implementation/QA. This is not a completed repair pipeline or SOP PASS.
