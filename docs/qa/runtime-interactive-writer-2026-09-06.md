# Runtime interactive writer bridge

Status: IN_PROGRESS; no native activation or real request in this checkpoint.

`InteractiveWriterService` now joins persisted pending story turns, runtime-owned
prompt construction, durable transport execution, response validation, actual
returned task/model declarations and per-episode draft/receipt persistence.
It rejects stale/non-pending turn revisions. The prompt excludes queued input
until claimed, receipt metadata and nested raw provider answers, without deleting
those records from local story history. No script is automatically approved.

The interruption test simulates a successful network response followed by failed
story save. A reconstructed service then recovers the completed response, retains
a subsequently queued supplement, and saves the draft plus bound receipt with
exactly one mock network call. A separate test verifies prompt projection does
not mutate history or include unclaimed/receipt data. Both tests and Ruff pass.

The prior full suite finished with 341 passing tests before these two additions.
New full CI, native endpoint wiring, project backup/restore treatment of execution
records, authenticated execution provenance and real Hops acceptance remain open.
The service does not set `provider_execution_verified` to true.
