# Story supplements while writing

Status: IN_PROGRESS; native timing QA remains required.

Previously a narrated supplement arriving while the assistant was working only
produced “please wait” and did not enter SQLite. The runtime now accepts queued
story inputs without advancing the active writer revision, so an in-flight
answer remains valid. Queue IDs are idempotent and conflicting reuse is rejected.
Promotion to a normal writer turn removes the queue item atomically with adding
the durable turn; restart does not erase queued inputs.

The native client queues narrated supplements while busy, drains them after
writing/lookup, and checks project identity plus selection generation before
continuing. A new narrated input after restart goes behind existing supplements.
Simply opening a project does not resubmit incomplete paid requests. Pending
supplements are visible in restored conversation history. Queue bodies are not
sent to the writer until promoted, preventing double consumption.

Limits: this handles narrated story supplements, not every specialized action or
approval intent. If initial project creation has not returned an ID, or saving
fails, the text is retained in the input area rather than falsely called saved.
Native simultaneous-input, project-switch and restart QA are still open.

Regression coverage: supplement insertion leaves active revision/status intact;
answer then succeeds; queue survives restart; repeated enqueue and promotion do
not duplicate text; conflicting IDs fail. Swift parsing, runtime tests and API
compatibility are checked separately from real native acceptance.

Local verification: 326 runtime tests passed; Swift parse, Ruff and OpenAPI
backward-compatibility checks passed. No native or real provider acceptance is
claimed from those results.
