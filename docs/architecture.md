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

Season and episode-plan edits append a full season-plan revision. Spoken and
visual approval records bind to one revision; any later edit makes that approval
visibly stale. Once an episode script is approved or enters production, its plan
fields are immutable even while later episodes continue to change.

SQLite changes are applied as numbered migrations and surfaced by the health
endpoint. Script confirmations are retained as separate approval audit records,
including approver identity, spoken confirmation and guardian authorization.
In the packaged application the single database is local at
`~/Library/Application Support/Nalu Voice Studio/nalu.sqlite3`; it is not an
upstream Qingshan database and is never synchronized automatically. The Runtime
creates bounded, immutable production packages from approved records instead of
giving the production line direct database access.

## Multi-episode inheritance

Assets belong to a project and may be scoped to a season or episode. Starting a
production run snapshots the resolved assets and latest continuity state. Later
asset edits do not mutate an in-flight or completed episode.

The current Runtime and native client implement managed project and episode
scope; season-specific scope remains an explicit SOP-05 gap. Imported bytes are
copied under the Runtime data root after path, MIME and size checks. Face and
voice consent actions are separate audit records. Revocation blocks new
production, while immutable run dependency snapshots prevent deletion from
silently rewriting production history.

The native continuity review has two deliberately separate forms. The opening
form starts from the latest earlier-episode snapshot and the ending form creates
a new immutable handoff snapshot. Both use typed character, prop, scene, time and
weather fields; the ending form also records unresolved hooks. Automatic
end-state extraction from the completed episode remains an SOP-06 gap, so the
current client requires a user-reviewed handoff instead of treating generated
text as authority.

Before a later episode script can be saved for production, its opening state is
audited against the inherited snapshot. Missing or changed wardrobe, location,
injuries, held props, relationships, revealed facts, prop ownership/condition,
scene, time or weather block the path. A transition explanation may resolve an
exact conflict path. The advanced override is fail-closed: its versioned record
must name exactly the current conflict paths, include a reason and reviewer, and
contain explicit confirmation language. The accepted opening state, explanations
and any override are stored in the immutable script revision and re-audited when
the production package is built.

Project libraries use the same authority boundary. Characters, scenes, props,
voices and styles have a stable project identity plus append-only revisions.
Editing creates a draft revision without silently replacing the last confirmed
revision. Confirmation must target the current revision and contain explicit
confirmation language. Source asset IDs must belong to the same project and
biometric sources must retain active consent; source memory cards must be
confirmed and authorized for story or visual use.

The native client lists the five project-library kinds in the project planning
surface. A typed entry or a two-question voice interview creates only a draft.
Nalu reads the name and description back; production authority is granted only
after a separate explicit “我确认/我同意” turn bound to the current revision.
Negative or ambiguous speech leaves the entry visible as an unconfirmed draft.

Confirmed entities may declare plain-language aliases. Resolution normalizes a
spoken mention and searches only confirmed revisions. Confirmation fails if a
name or alias collides with another confirmed entity of the same kind; unknown
mentions return not-found instead of inventing a match. This is the first
fail-closed entity-resolution gate. Relationship/date/event contradiction
reasoning across memory cards remains an explicit SOP-06 gap.

At production-package creation, the Runtime resolves only confirmed library
revisions. That resolved set is hashed into the package and emitted into the
corresponding Qingshan character, scene, prop, audio and visual-style indexes.
Later library edits therefore affect only future packages and cannot mutate a
completed episode workspace.

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
