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

Added read-only `/repair-shot-draft/context` for native clients to obtain exact
source event and immutable package hashes without reading local filesystem paths.
Runtime recreation/context identity and non-repair rejection added;3 cases pass4.28s.
Native transport now performs scoped context GET followed by draft POST and rejects
wrong parent, invalid digests or an approved/authorized response. Native transport
tests and UI recovery after partially completed preparation still need wiring;
do not mark the interactive journey complete. No automatic paid calls.
