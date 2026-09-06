# Reviewed episode plan → concrete video request binding

Status: IN_PROGRESS; synthetic network and local contract evidence only.

Local verification: full pytest **426 passed in 58.65s**, two existing
deprecation warnings; Ruff, OpenAPI contract and diff checks passed. Native
compilation, current implementation CI and live production remain unverified.

When a run has any interactive shot-plan event, preparing a concrete video task
now requires the newest `shot_plan_approved` event ID and canonical plan digest.
Draft, revised-but-unconfirmed, obsolete, unbound or wrong-package plans fail.
The task key must map to exactly one saved shot; its duration and complete
reviewed video description must be preserved in the compiled provider prompt.
Existing professional imports with no interactive shot plan retain their full
compiler validation path; that path cannot bypass a plan already present.

The preparation digest includes the approval event, plan digest and shot index.
Dispatch reconstructs the binding from the saved preparation rather than from
new caller text. It revalidates before durable submission, and checks again
immediately before the provider POST. Existing submitted/uncertain tasks remain
read-only on replay. No new provider retry or cost authorization is introduced.

`test_paid_submitter_boundary.py` covers bound preparation and approved-price
dispatch, unconfirmed/unbound/obsolete plans, wrong prompt/duration and unknown
task rejection. Fixtures explicitly synthesize a saved approval to isolate this
boundary; they do not prove real model content, user approval or image quality.
The existing budget fixture tried to prepare unrelated extra shots on a one-shot
plan and correctly failed; the plan case now asserts that rejection, while the
original no-plan fixture still verifies concurrent budget exhaustion.

The prompt inclusion check is a preservation check, not a semantic proof that
additional compiler text does not contradict the reviewed description. Existing
camera/prop/continuity checks remain necessary. Actual plan-to-full-contract
compilation, entry-frame generation and continuity frame chaining are still open,
as are native CI/UI QA, real provider generation, master QA and controlled release.
No SOP status is promoted by this change.
