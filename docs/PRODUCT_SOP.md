# Nalu Voice Studio product completion SOP

This file is the completion authority for the product. A milestone is not the
product. An item becomes `PASS` only when implementation, tests, documentation,
and required QA evidence all exist. Every heartbeat revalidates completed items
against the current main branch.

## Status vocabulary

- `TODO`: not started.
- `IN_PROGRESS`: implementation or QA is incomplete.
- `WAITING_AUTHORIZATION`: blocked only on an explicit user-controlled action.
- `PASS`: every acceptance criterion and evidence requirement is satisfied.
- `REGRESSION`: previously passed, but current verification fails.

## Global completion rule

The project is complete only when SOP-00 through SOP-12 are all `PASS` on the
same release candidate. `WAITING_AUTHORIZATION` is not complete. A green CI run
is necessary but not sufficient.

---

## SOP-00 · Open-source foundation — PASS

Acceptance:

- Public repository, MIT license, provenance, governance and security policy.
- Contribution guide, Code of Conduct, issue and PR templates.
- Python and macOS CI required on pull requests.
- No credentials, user media, voice samples, receipts or runtime state tracked.

Evidence:

- Commit: `d94e66c`
- GitHub CI: run `33269963489`, runtime and macOS jobs passed.

## SOP-01 · Versioned product domain and Runtime API — IN_PROGRESS

Acceptance:

- Project → Season → Episode hierarchy with stable IDs.
- Versioned scripts and explicit approval audit records.
- Episode lifecycle transitions are validated, persisted and recoverable.
- Production events are ordered and resumable after process restart.
- OpenAPI contract is exported and checked for unreviewed breaking changes.
- SQLite schema migrations preserve existing projects.

QA:

- API contract, concurrency, restart recovery, migration and negative tests.
- Real HTTP smoke test against a clean data directory.

Current evidence:

- Stable hierarchy, script revisions, approval audit records and schema migration v1.
- Committed OpenAPI snapshot with CI freshness check.
- Ordered concurrent production-event test and clean-directory real HTTP smoke test.
- Still required before `PASS`: complete lifecycle transition table, idempotent mutation
  contract, restart recovery suite and reviewed compatibility policy.

## SOP-02 · Voice interview and accessible conversation — IN_PROGRESS

Acceptance:

- Push-to-talk and optional local speech recognition.
- One-question-at-a-time interview state machine.
- Spoken correction, repeat, back, pause and resume.
- Visible transcript and confidence/failure recovery.
- Older-adult usability: large targets, plain language and keyboard-free path.
- Child mode: guardian setup and age-appropriate prompts.

QA:

- Unit tests for interview state and interruption recovery.
- Voice-only completion of a sample project on a clean Mac user account.
- Accessibility Inspector and VoiceOver report.

Current evidence:

- Native push-to-talk, visible transcript, large controls, repeat action and a
  one-question-at-a-time project setup state machine.
- Still required before `PASS`: correction/back/pause semantics, confidence recovery,
  guardian interview, VoiceOver audit and clean-account voice-only QA.

## SOP-03 · Multi-project, season and episode planning — IN_PROGRESS

Acceptance:

- Create, open, rename, archive, export and restore projects.
- Generate and edit season arcs and episode outlines.
- Voice and visual approval of the season plan.
- Independent status and progress for every episode.
- Changing a future episode cannot mutate an approved or produced episode.

QA:

- A 10-episode project survives application restart and export/import.
- Concurrent episode planning has no numbering or state collision.

Current evidence:

- Voice answers atomically create a persisted Project → first Season → numbered
  Episode plan; existing projects and episode selectors reload from the Runtime API.
- Still required before `PASS`: rename/archive/export/restore, editable season arcs,
  plan approval, restart/import QA and immutable-future-edit tests.

## SOP-04 · Script creation, review and approval — TODO

Acceptance:

- Interview transcript becomes project bible, season plan and episode drafts.
- Script revisions retain provenance and approved narrative authority.
- Nalu can read a plain-language episode summary aloud.
- User corrections create a new revision without overwriting history.
- Production cannot start from an unapproved revision.

QA:

- Approval, revocation, stale revision and child guardian negative tests.
- Human review confirms the spoken summary matches the locked script.

## SOP-05 · Media assets, consent and privacy — TODO

Acceptance:

- Local import for photos, audio, documents and reference video.
- Project, season and episode asset scopes.
- Face and voice consent receipts with revocation.
- Guardian authorization for child biometric data.
- Local encryption strategy and Keychain-managed secrets.
- Deleting an asset identifies every dependent, immutable production snapshot.

QA:

- Unauthorized biometric use and path traversal tests fail closed.
- Privacy export and complete project deletion verification.

## SOP-06 · Cross-episode inheritance and continuity — TODO

Acceptance:

- Project libraries for characters, scenes, props, voices and styles.
- Immutable resolved-asset snapshot per production run.
- Episode end-state captures wardrobe, location, injuries, prop ownership,
  relationships, revealed facts, time/weather and unresolved hooks.
- Next-episode preflight rejects unexplained continuity conflicts.
- Explicit, versioned override path with user review.

QA:

- At least three multi-episode continuity fixtures with positive and negative cases.
- Regression verifies completed episodes do not change after library edits.

## SOP-07 · Productized Qingshan execution adapter — IN_PROGRESS

Acceptance:

- Pinned upstream source and capability manifest verified by hash.
- Nalu production package materializes a clean Qingshan workspace.
- No product path depends on E40/E41-specific filenames or absolute user paths.
- SD2 Pro and MiniMax-H3 compile through separate adapters.
- Preflight invokes required Qingshan gates and stores machine-readable evidence.
- Durable transaction submitter is the only paid POST path.

QA:

- Offline contract fixtures pass without credentials or paid calls.
- Authorized sandbox generation binds transaction, task ID, result and credit receipt.
- Duplicate submission, stale package and model-policy conflicts fail closed.

Current evidence:

- Pinned upstream snapshot, capability checks, immutable Nalu package, clean
  per-run workspace materializer and SHA-256 preflight evidence.
- Still required before `PASS`: separate SD2 Pro/H3 compilers, full registered gate
  execution, durable paid-transaction binding and authorized sandbox evidence.

## SOP-08 · Production jobs, progress, cancellation and recovery — IN_PROGRESS

Acceptance:

- Persistent ordered events for every production run.
- Observable stages, progress, current action and user-facing explanation.
- Safe cancellation and resumable checkpoints.
- Application and runtime restarts do not lose remote task bindings.
- Retry policy distinguishes zero-charge failure, ambiguous charge and completed task.

QA:

- Crash/restart tests at every paid transaction boundary.
- Event sequence and idempotency tests under concurrent requests.

Current evidence:

- Ordered persistent events, cancellation, preflight resume and concurrent writer test.
- Still required before `PASS`: durable remote bindings, transaction-boundary crash tests,
  ambiguous-charge reconciliation and stage-level progress.

## SOP-09 · Postproduction and release-blocking QA — TODO

Acceptance:

- Shot selection, normalized media, dialogue, ambience, foley, music and subtitles.
- Final MP4 normalization and timestamp checks.
- Identity, wardrobe, space/axis, pose, prop, sound and transition QA evidence.
- ASR/VAD, subtitle, frame-repeat and media-boundary checks.
- Failed gates produce specific repair tasks and cannot be bypassed silently.

QA:

- Golden media fixtures for pass/fail cases.
- Human audiovisual review of original-resolution final master.

## SOP-10 · Controlled release and learning loop — TODO

Acceptance:

- Export master, cover, captions, title, description and release package.
- Publishing requires separate, platform-specific approval.
- Child projects require guardian publishing approval.
- Published identifiers and states are verified and stored.
- Platform metrics feed a versioned next-episode director strategy.

QA:

- Dry-run platform adapters and duplicate/replacement protection tests.
- Authorized test-channel publication and state reconciliation evidence.

## SOP-11 · macOS packaging, updates and operations — TODO

Acceptance:

- Runtime bundled and supervised by the macOS application.
- Signed, hardened and notarized universal application.
- First-run permissions, model/runtime setup and diagnostics.
- Safe automatic updates and data migrations.
- Backup, restore, disk-space warning and long-running background behavior.

QA:

- Clean installation on supported Apple Silicon macOS versions.
- Upgrade and rollback rehearsal with a populated multi-episode project.

## SOP-12 · End-to-end release-candidate acceptance — TODO

Acceptance scenarios:

1. Older adult creates a personal autobiography using voice and personal photos.
2. Guardian and child create a fictional multi-episode story.
3. A 10-episode project preserves identity, voice and narrative state across episodes.
4. One episode fails generation, survives restart, resumes safely and passes QA.
5. Approved final media exports and publishes without duplicate paid calls.

Completion evidence:

- All scenarios run from a clean signed installation.
- Costs, task IDs, receipts, QA reports and published IDs reconcile.
- No P0/P1 defects remain open.
- SOP-00 through SOP-11 are revalidated on the same release commit.
