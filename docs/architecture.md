# Architecture

## Boundary

The product never exposes individual historical Qingshan scripts to a client.
The local Runtime API owns identity, lifecycle, persistence, approval, and
package creation. The Qingshan adapter consumes a versioned immutable package.

```text
SwiftUI voice client
        │ localhost + bearer session
        ▼
Qingshan Runtime API
        ├── projects / seasons / episodes
        ├── script revisions and approvals
        ├── project asset registry
        ├── continuity snapshots
        └── production-run state machine
                │ immutable package
                ▼
Qingshan adapter
        ├── clean workspace materializer
        ├── preflight and continuity gates
        ├── durable paid submitter
        ├── generation and assembly
        └── QA and release evidence
```

## Authority hierarchy

1. User-approved project bible.
2. User-approved episode script revision.
3. Immutable episode production package.
4. Qingshan run receipts and QA evidence.

A downstream tool may enrich directing and generation contracts, but it may not
silently alter an approved narrative authority.

SQLite changes are applied as numbered migrations and surfaced by the health
endpoint. Script confirmations are retained as separate approval audit records,
including approver identity, spoken confirmation and guardian authorization.

## Multi-episode inheritance

Assets belong to a project and may be scoped to a season or episode. Starting a
production run snapshots the resolved assets and latest continuity state. Later
asset edits do not mutate an in-flight or completed episode.

At episode completion, the production line writes an end-state snapshot for the
next episode: character location and wardrobe, injuries, prop ownership,
relationship changes, revealed facts, time/weather, and unresolved hooks.

## Workspace materialization

Every run produces a clean `qingshan-workspace/` containing the approved script,
work queue, task record, project asset indexes, inherited continuity, production
policy, and a SHA-256 workspace manifest. Product paths use stable episode IDs
and never call imported E40/E41-specific commands directly.

## Continuous upstream productization

Qingshan is an evolving upstream capability source, not a copied application
surface. Nalu checks releases daily. Each candidate is quarantined, diffed and
classified into capability additions, contract changes, migrations and unsafe
historical assumptions. The reviewed release, commit, whole-tree digest and
critical capability hashes are pinned in `configs/qingshan-upstream.json`.

An upgrade reaches `vendor/qingshan` only after upstream fixtures, Nalu package
contracts, model policy, Runtime regression, macOS build and relevant end-to-end
QA pass. Paid execution remains disabled throughout automated upgrade work.

## Safety

- Face and voice assets require explicit consent metadata.
- Child-owned biometric assets require guardian approval.
- Paid calls and publishing are separate approval scopes.
- Paid production requires a persisted, payload-bound idempotency key before any
  external transaction may be opened.
- The default adapter is dry-run and produces no paid POST.
- Secrets are never stored in project JSON or source control.
