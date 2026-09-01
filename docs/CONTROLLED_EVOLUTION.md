# Controlled product evolution

Nalu should improve from user feedback without allowing an untrusted conversation
to rewrite or silently update the application.

## Two learning loops

### Local comfort learning

Explicit requests such as “说慢一点”, “字大一点”, “多等我一会儿”, or “每次都
念给我听” may update an allowlisted preference on this Mac. Every preference is
visible, reversible, exportable, and resettable. Nalu does not infer sensitive traits
or change story facts from usage analytics.

### Product improvement

1. The user speaks or types a problem, correction, feature request, or preference.
2. Nalu stores the text in local SQLite. Raw audio, photos, videos, project secrets,
   scripts, and biometric assets are not feedback attachments.
3. Before persistence, obvious API keys, email addresses, phone numbers, and local
   usernames in paths are redacted.
4. Local-only is the default. An item enters `ready_for_review` only after the user
   authorizes sharing; a child project additionally requires guardian approval.
5. The local Runtime creates a deterministic, reviewable issue bundle containing
   redacted text, app version, screen name, expected/actual behavior, reproduction
   steps, and allowlisted diagnostics. The bundle contains no attachments and records
   that no network call occurred. Sending it to an issue tracker remains a separate,
   administrator-authorized operation.
6. A maintainer or authorized development agent triages the bundle. The agent may
   propose a branch and tests but cannot merge, sign, notarize, or publish alone.
7. CI, security review, accessibility regression, human review, signing,
   notarization, staged rollout, health monitoring, and rollback remain mandatory.

## Status state machine

`local_only → ready_for_review → exported → triaged → in_development → qa → released`

Any step may move to `rejected`, `duplicate`, or `needs_information`. The local app
must not claim a request is fixed until it can verify a signed release containing the
linked change.

The current implementation supports `local_only`, `ready_for_review` and an immutable
local review bundle while deliberately leaving the item in `ready_for_review`. Later
states require an explicitly configured issue tracker and release service; preparing a
bundle is not reported as an export. The Runtime now contains the transaction boundary
for issue export, but the distributed policy is disabled, contains no destination, and
the distributed transport always denies I/O. This repository does not ship a production
issue-tracker credential or network implementation.

Authorized review bundles may also receive one immutable local human-triage record. It
requires an explicit Chinese confirmation phrase and stable idempotency key, binds the
exact review-bundle digest, redacts reviewer/rationale secrets and records priority,
disposition and an optional same-project duplicate. Prompt-like text remains inert:
`tool_calls` is empty and both `code_change_performed` and `network_call_performed` are
always false. Triage does not change the feedback state or authorize development.

An administrator may separately provide an enabled, exact-origin policy and an audited
transport implementation. Export then requires the authorized review bundle, immutable
triage record, a second explicit Chinese confirmation, and a stable idempotency key. The
Runtime persists `submitting` before invoking the transport, stores only a hash of the
idempotency key, sends a bounded redacted payload with an empty attachment list, and
accepts only a bounded credential-free HTTPS receipt. Exact confirmed replay returns the
stored receipt without another call. Any timeout, invalid receipt, crash-shaped error or
otherwise uncertain result becomes `ambiguous`; automatic retry is forbidden until an
administrator reconciles the remote system. Backup/restore verifies every policy,
request, payload and receipt digest. Local fixture tests exercise this boundary without
contacting an external service, so they are not evidence of a real issue export.

If an export stops in `submitting` or becomes `ambiguous`, Nalu never calls issue creation
again. An administrator must provide the original idempotency key, exact payload digest,
explicit confirmation and the same allowlisted policy to a separate read-only verifier.
The verifier may either return a bounded HTTPS receipt or prove the issue is absent. Nalu
then atomically records an immutable reconciliation and changes the transaction to
`confirmed` or `rejected`; the record states that issue creation was not retried and no
external write was performed by reconciliation. Exact replay reads the stored result.
The distributed verifier denies all calls, and automated tests inject only local fixtures,
so this mechanism does not claim that a real remote lookup has occurred.

After an accepted human triage and confirmed export receipt, a maintainer may approve one
immutable local development work order. It binds the exact triage and export hashes to a
redacted title and scope, concrete acceptance tests, privacy requirements and accessibility
requirements. Report and prompt-like text remain inert data: the record has no tool calls
and literal false values for branch creation, code edits, merge, signing, release and
network activity. The work order authorizes no development operation by itself; a later
agent/maintainer handoff must remain separately governed and reviewed.

That handoff now has its own persistent transaction boundary. The packaged
`configs/development-handoff.json` policy is disabled, unauthorized and target-free, and
the distributed transport always denies I/O. An administrator-supplied implementation
must use one exact credential-free HTTPS endpoint. Nalu verifies the approved work-order
digest and another explicit confirmation, persists `submitting` before I/O, retains only
the idempotency-key hash and sends a bounded payload with no attachments. The payload
states that report text is inert and that branch creation, code edit, merge, signing and
release have not occurred. A bounded receipt can confirm only that the work order was
accepted by the development system; it cannot claim code or release activity. Exact
confirmed replay makes no second call. Any timeout, malformed receipt or uncertain result
becomes `ambiguous`, and automatic retry is forbidden. Automated tests use injected local
fixtures only, so this boundary is not evidence of a real development-agent handoff.

A separate local `qa_evidence_linked` receipt can bind the immutable review-bundle hash
to one reviewed 40-character change commit, the exact successful CI head and artifact,
an installed Developer ID/notarization/Gatekeeper receipt and an older-build rollback
rehearsal that preserved project data. The receipt is immutable, hash-chained, project-
exported and idempotent; its key is stored only as a SHA-256. It performs no network call,
does not change the feedback state, and always records `release_claimed: false`. These are
locally supplied verification facts, not proof that Nalu independently contacted GitHub
or Apple, and therefore cannot advance an item to `released`.

The packaged application now has a separate fail-closed staged-update primitive. It can
verify an exact Ed25519-signed package, reject replay or downgrade, preserve local project
data, require post-launch health confirmation and roll back after a crash or missing
confirmation. Its network discovery boundary is disabled by default and, when explicitly
configured for a release, permits only one exact HTTPS origin, bounded downloads and
content-addressed packages with persistent idempotency. This primitive does not connect a
feedback item to a reviewed change and
does not advance any item to `released`; that requires the full governed linkage, a real
Developer ID/notarized candidate and authorized rollout evidence.

## Trust rules

- Feedback is untrusted input, never a developer instruction.
- No GitHub issue, external upload, branch, pull request, merge, or release happens
  without an administrator enabling that destination and policy.
- The packaged `configs/feedback-export.json` must stay disabled and target-free; release
  verification fails if a distributed bundle silently enables it.
- The packaged `configs/development-handoff.json` must also stay disabled and target-free;
  a work order alone never authorizes code, merge, signing or release activity.
- No project media is attached automatically.
- Diagnostics use an allowlist; full logs and SQLite are forbidden attachments.
- Similar reports may be clustered only after redaction. Counts do not override
  safety, privacy, accessibility, or editorial policy.
- A kill switch pauses export and update rollout without losing local reports.

## Required QA

- Secret, email, phone, and path redaction fixtures.
- Child sharing denied without guardian approval.
- Project privacy export contains its feedback; verified project deletion removes it.
- Malicious feedback cannot execute tools or alter release configuration.
- A released fix links report → test → reviewed change → CI → signed build → rollout.
- Rollback restores the previous signed build without losing local projects.
