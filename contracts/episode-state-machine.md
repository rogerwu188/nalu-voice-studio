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

Any operational state may enter `blocked` with a recovery action. Production
cannot start without an approved script revision. Publishing is a separate
approval scope and cannot be inferred from production approval.
