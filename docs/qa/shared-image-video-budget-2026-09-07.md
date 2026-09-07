# Shared image/video estimate envelope

Status: IN_PROGRESS — implementation and synthetic tests, not paid production.

The saved-image preparation now has a native estimate-confirmation endpoint:
`POST /v1/production-runs/{run_id}/image-task-preparations/{preparation_id}/estimate-approvals`.
The runtime re-materializes the current confirmed shot, script and inherited
image references before reserving its exact request SHA. No API key or provider
call is needed for this local confirmation. Child projects require guardian
confirmation, and changed/obsolete/cancelled/archived contexts are refused.

Image and video reservations now sum against the same confirmed run budget under
SQLite `BEGIN IMMEDIATE`; they no longer independently consume the full envelope.
Repeated confirmation after restart reuses the same reservation; conflicting
amounts/preparations require reconciliation. Existing reservations that exceed a
subsequently reduced budget are also refused on revalidation.

These are **user-confirmed estimates**, not verified account prices or a provider
hard charge cap. `provider_price_verified`, `provider_charge_cap_guaranteed`,
`upstream_image_contract_verified` and `generation_performed` remain false. There
is still no public image-submit endpoint: the complete QingShan image/identity/
scene/entry-state contracts and concrete price observation must be wired first.
This checkpoint must not be used as permission to bypass those requirements.

Initial tests: 12 passed in 2.64s, covering both image-first/video-first budget
consumption, exact combined limit, concurrent duplicate confirmation, restart,
changed estimate/plan/hash, cancellation, over-budget and guardian handling.
All sources and approval records are synthetic; there was no real generation.
Ruff and OpenAPI backward compatibility passed. Full regression result follows
when the currently running test process completes.

Native confirmation UI, live provider pricing, submitted-task cost reconciliation
and real image-to-video/master/release acceptance remain outstanding.

Full local regression: **526 passed in 70.69s**. The final targeted run added
reduced-budget revalidation for both image and video and passed **13 cases in
2.88s**; that additional test was not in the earlier full-suite collection.
