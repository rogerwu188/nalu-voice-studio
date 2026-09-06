# Story supplements while writing

Status: IN_PROGRESS; native timing QA remains required.

Previously a narrated supplement arriving while the assistant was working only
produced “please wait” and did not enter SQLite. The runtime now accepts queued
story inputs without advancing the active writer revision, so an in-flight
answer remains valid. Queue IDs are idempotent and conflicting reuse is rejected.
Promotion to a normal writer turn removes the queue item atomically with adding
the durable turn; restart does not erase queued inputs.

The native client queues narrated supplements and web-source requests while busy, drains them after
writing/lookup, and checks project identity plus selection generation before
continuing. New narration or web-source input after restart goes behind existing
supplements. Each queue item retains its source mode: web-source items dispatch
to lookup with the original durable turn ID, not directly to the story writer.
Simply opening a project does not resubmit incomplete paid requests. Pending
supplements are visible in restored conversation history. Queue bodies are not
sent to the writer until promoted, preventing double consumption.

Limits: this handles narration and web-source requests, not every specialized action or
approval intent. If initial project creation has not returned an ID, or saving
fails, the text is retained in the input area rather than falsely called saved.
Native simultaneous-input, project-switch and restart QA are still open.

Regression coverage: supplement insertion leaves active revision/status intact;
answer then succeeds; queue survives restart; repeated enqueue and promotion do
not duplicate text; conflicting IDs fail. Restart/promotion coverage runs for
both narrated and web-source modes. Swift parsing, runtime tests and API
compatibility are checked separately from real native acceptance.

Local verification after web-source queue extension: 329 runtime tests passed;
Swift parse and Ruff passed. The earlier narration checkpoint also passed OpenAPI
backward-compatibility checks. No native or real provider acceptance is
claimed from those results.
