# Approved episode → durable AI shot draft

Status: IN_PROGRESS, backend/mock-network evidence only.

Local verification: full pytest **419 passed in 53.72s**, with two existing
Starlette/AnyIO deprecation warnings; Ruff and OpenAPI contract checks passed.
Current implementation CI and native QA are not yet verified.

`POST /v1/production-runs/{run_id}/shot-plans` accepts a writer model and a
transient `X-Nalu-Writer-Key`, never a caller-supplied script or approval. It
reads the current local production package and the actual approved episode
revision. Hops receives only the approved text, duration, style/aspect ratio,
asset IDs/kinds/names and a strict output schema, not private interview caches,
local media paths or the entire project bible. Origin-bearing requests and
missing credentials are rejected. No credentials are persisted in the plan.

The runtime-owned writer execution ledger persists intent before model I/O.
The run-scoped execution ID and exact request digest prevent automatic repeated
model calls after interruption or an uncertain outcome. Repeated successful
requests replay the response and return the same saved plan event. A changed
request is a conflict, not permission to silently invoke again.

Each draft shot has a literal approved-script excerpt, 4–15-second duration,
scene, entry/action/exit, camera, speech/sound, entry-frame and video prompts,
asset references and transition type. Durations must sum to the episode target.
Unknown assets, invented excerpts, empty mandatory descriptions, additional
authority fields and inconsistent continuous entry states are rejected.
Runtime-assigned task keys and time spans are separate from model output.
Continuous shots explicitly depend on the preceding final frame. The package,
latest run, archive state and episode revision/duration are rechecked before
adopting the response. Changed packages fail closed with a redacted conflict.

Evidence: `tests/test_shot_planning.py` uses an isolated SQLite database and
`httpx.MockTransport`; no paid model, image, video or publication operation.
Cases cover success and restart, exact continuity linkage, incorrect duration,
invented source/asset, model-claimed QA, HTTP 401, illegal first-shot continuity,
blank prompt and package corruption during the request. Every case makes at
most one HTTP attempt across runtime restart. Existing story-writer validation
remains the transport default; only this runtime route selects shot validation.

Remaining: real Hops account acceptance (previous writer request returned 401),
native orchestration and review/edit UI, complete structured camera/prop
authority compilation, entry-frame generation, provider-bound input preparation,
real approved generation, master QA and release. Source substring checks are
not proof of semantic fidelity or coverage of every script detail. The 120-shot
schema and bounded token response do not yet establish long-episode planning.
Draft events explicitly mark approved/frames_generated/generation_performed
false. The LLM planner invocation is distinct from video generation. This is
not SOP completion or same-candidate native E2E evidence.
