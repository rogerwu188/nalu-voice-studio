# Native spoken character correction

IN_PROGRESS. Source flow implemented; current Swift CI and real native QA pending.

During character confirmation, an explicit correction request enters a complete
description capture step. Nalu asks for the revised description instead of trying
to treat “not right” as approval or silently infer a partial fact replacement.
The new revision retains the person's name, attributes, source photo/memory links,
and exact heard current revision. The response is read back and requires separate
confirmation. No model or new voice engine is invoked.

Failed saves retain the pending request during this active conversation; explicit
retry uses the identical expected revision. Concurrent later edits cannot be
overwritten. Project selection clears stale confirmation/correction queues and
asynchronous results are checked against the selection generation. This is not
a claim of durable recovery for unsent dictation after application termination.

Impeccable hardening guidance influenced input/error preservation and recovery
language; no new professional form or visual redesign was added.

Evidence:

- 23 project-library/planning backend tests passed in 13.35s; Ruff/diff checks passed.
- Native helper tests added for preserved sources, revision binding, unchanged old
  facts, whitespace/oversize input and correction-vs-confirmation commands.
- Swift tests are not locally executed because of the known installed toolchain
  failure. Prior `2e70126` CI 34078486993 ARM passed, Intel/runtime still running at
  inspection; these changes require their own CI and interaction evidence.

Next: current CI/native correction QA; reconcile the production snapshot after
confirmed character changes without losing approved shots or duplicating tasks;
compose real accepted assets/frames and per-shot production requests. No real
provider/payment/publication call made. No SOP promoted to PASS.
