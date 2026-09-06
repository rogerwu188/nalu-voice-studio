# Interactive writing checkpoint — IN_PROGRESS

User priority: narrated story and online source inputs must lead to interactive
episode writing, then confirmed production and controlled release. Existing TTS
is the baseline. This checkpoint is not that completed workflow.

Implemented:

- SQLite project-owned conversation, revision checks and payload-bound turn IDs.
- Restart recovery, retained drafts on lookup/writer failure, stale-answer rejection.
- Native runtime client and project-bound saving of research requests/results.
- Late research results do not appear in a newly selected project.
- Existing projects do not get the idle "create new project" resume instruction.

Local evidence: full runtime suite **315 passed** (including two new interactive
story regressions); Ruff and Swift parse passed.
Added two Swift regression tests; compiled execution belongs to CI, not parse.
CI results and native QA remain pending; no SOP is promoted.

Still missing: actual interactive AI writer integration, source retrieval capability
verification against configured service, source selection/rights handling, automatic
draft display and honest AI-provenance handoff into script revisions. Real native
two-path QA and production/release demonstration remain open. No paid request,
generated video or release is claimed by these synthetic tests.

API request documentation inspected for the next writer step:
[Chat Completions](https://developers.openai.com/api/reference/typescript/resources/chat/subresources/completions/methods/create).
This documentation does not establish third-party provider compatibility.
