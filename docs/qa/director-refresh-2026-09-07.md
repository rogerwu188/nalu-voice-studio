# Version-bound director refresh — implementation checkpoint

Status: IN_PROGRESS. Not a real provider, native UI, video or release acceptance.

The native-only `POST /v1/production-runs/{run_id}/shot-plans/{source_id}/director-refresh`
accepts the exact source-plan hash and configured model. Only missing director
objects may be filled. User descriptions, timing, shot order, designs and already
present director choices must remain identical. The result is a new unapproved
revision, never image QA or spending authority.

The existing persistent writer ledger binds the request body and endpoint to one
run/source execution ID. A completed response is recoverable without another POST;
an ambiguous attempt is not automatically resubmitted. A model change cannot bypass
the same source's durable attempt. The atomic local review checks the current plan,
approved script/package and downstream production locks again before adoption.

Evidence (synthetic provider only):

- `pytest -q tests/test_shot_planning.py tests/test_director_draft.py`:
  **26 passed in 16.74s**.
- Cases include successful refresh/restart, attempted user-text rewrite, HTTP 401,
  concurrent user edit, interruption after durable model response but before plan
  save, downstream submission lock, changed model replay and native credential gate.
- Ruff passed; exported OpenAPI backward-compatible with parent HEAD `096b478`.
- No real model request, image generation, video submission or publication performed.

Next: native save → refresh orchestration with preserved edits and honest readback;
full regression/CI; compile reviewed director choices with independently verified
assets/frame evidence into the production contract. Mac UI acceptance remains
unverified and the existing Hops 401 must not be silently retried.
