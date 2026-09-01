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
bundle is not reported as an export.

The packaged application now has a separate fail-closed staged-update primitive. It can
verify an exact Ed25519-signed package, reject replay or downgrade, preserve local project
data, require post-launch health confirmation and roll back after a crash or missing
confirmation. This primitive does not connect a feedback item to a reviewed change and
does not advance any item to `released`; that requires the full governed linkage, a real
Developer ID/notarized candidate and authorized rollout evidence.

## Trust rules

- Feedback is untrusted input, never a developer instruction.
- No GitHub issue, external upload, branch, pull request, merge, or release happens
  without an administrator enabling that destination and policy.
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
