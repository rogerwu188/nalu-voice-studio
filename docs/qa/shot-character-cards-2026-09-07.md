# Reviewed plan → local character cards

IN_PROGRESS. Backend implemented; native conversational handoff still required.

`POST /v1/production-runs/{run_id}/shot-plans/{source_id}/character-cards`
derives character drafts from the exact current approved plan. New cards retain
the source excerpt/design key and any project-owned linked photo. Existing named
characters retain their original descriptions, revisions and confirmation state.
Returned Chinese readback asks the user to check identity and correct the draft;
it never asserts that generated character details are confirmed family facts.

All inserts and the preparation event share one SQLite transaction. An identical
source request replays the saved result without duplicate people or generation.
The original production package remains unchanged. Character confirmation,
likeness/voice consent and paid approval are not inferred from plan approval.

Evidence:

- Planning + project library tests: 22 passed in 27.65s before final existing-card
  assertions; final planning rerun: **18 passed in 15.11s**, including preserved
  existing family facts, unconfirmed new drafts, replay, wrong hash/unapproved plan
  rejection and unchanged package bytes.
- Ruff, whitespace and backward-compatible OpenAPI checks passed.
- Previous full Python session 91694 completed **626 passed in 220.81s**. That run
  was collected before this new character-card implementation; not its full suite.
- Prior native `0a15e68` CI 34075561888 completed successfully. Current CI/native QA
  and real provider acceptance remain pending.

Next: call this endpoint from the native approved-plan workflow and read cards
through existing local TTS/library confirmation; then reconcile a new immutable
production snapshot with confirmed characters without losing the shot plan or
duplicating tasks. No model/provider/payment/publication request was made here.
