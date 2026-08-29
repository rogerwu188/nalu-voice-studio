# Episode state machine

```text
planned
  → script_draft
  → script_review
  → script_approved
  → preproduction
  → generating
  → postproduction
  → qa_review
  → ready_to_publish
  → published
```

Every transition is persisted as an ordered episode event. A new script revision
may return `script_approved` to `script_review`. Operational states may enter
`blocked`, but recovery must name the target state, actor and reason.

`script_approved` is reachable only through the script-approval endpoint.
`published` is reserved for the future platform-specific publishing approval
endpoint. Production preflight is the only normal path from `script_approved`
to `preproduction`; skipped or stale transitions fail with HTTP 409.
