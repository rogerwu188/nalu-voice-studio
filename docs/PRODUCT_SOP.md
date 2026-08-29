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

The project is complete only when SOP-00 through SOP-13 are all `PASS` on the
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
- Revalidated on commit `60f4626`: GitHub CI run `33272141000`, runtime and
  macOS jobs passed.

## SOP-01 · Versioned product domain and Runtime API — PASS

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
- Commit `1f2b8d5`: persisted lifecycle transitions, schema migration v2,
  concurrency-bound project-plan idempotency, restart recovery test and executable
  backward-compatibility check for the committed OpenAPI contract.
- Commit `e71c91e`: schema migration v3 and payload-bound production-run
  idempotency; paid production now rejects requests without an idempotency key.
- GitHub CI run `33272141000`: 12 Runtime tests, real loopback HTTP smoke,
  OpenAPI freshness/compatibility and full macOS build passed.
- Commit `6e5ecb7`: restart-safe production replay and populated v1 → v3
  migration rehearsal preserve projects, approved scripts and approval records.
- GitHub CI run `33272328616` on commit `9594e33`: 13 Runtime tests, real HTTP
  smoke, compatibility gates and full macOS build passed.

## SOP-02 · Voice interview and accessible conversation — IN_PROGRESS

Acceptance:

- Push-to-talk and optional local speech recognition.
- One-question-at-a-time interview state machine.
- Spoken correction, repeat, back, pause and resume.
- Visible transcript and confidence/failure recovery.
- Older-adult usability: large targets, plain language and keyboard-free path.
- Child mode: guardian setup and age-appropriate prompts.
- Optional cloud Realtime speech-to-speech mode with interruption and an explicit
  fallback to the local push-to-talk path.

QA:

- Unit tests for interview state and interruption recovery.
- Voice-only completion of a sample project on a clean Mac user account.
- Accessibility Inspector and VoiceOver report.

Current evidence:

- Native push-to-talk, visible transcript, large controls, repeat action and a
  one-question-at-a-time project setup state machine.
- Spoken pause/resume, repeat, back/correct commands and visible low-confidence
  recovery are implemented in the native interview flow.
- Commit `f69c113`, GitHub CI run `33273219260`: pure interview reducer with
  automated Swift tests for voice-only setup, interruption recovery and corrections.
- Audience routing now includes an explicit child/guardian identity and consent
  interview that fails closed before collecting the child's story.
- Commit `9a70b08`, GitHub CI run `33275504662`: the microphone flow now edits
  season and episode plans and records explicit voice approval. Ambiguous speech,
  negative speech and child approval without guardian presence fail closed in Swift tests.
- Still required before `PASS`: VoiceOver/Accessibility Inspector audit and a
  clean-account voice-only QA session with real microphone permissions.

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
- Voice intent distinguishes short drama, animation and commercial projects without
  silently routing an unsupported format to a paid production adapter.

Current evidence:

- Voice answers atomically create a persisted Project → first Season → numbered
  Episode plan; existing projects and episode selectors reload from the Runtime API.
- Commit `755b52d`, GitHub CI run `33274124753`: local rename, archive, versioned
  digest-checked export/restore and the 10-episode clean-database restart rehearsal passed.
- Commit `020bb3b`: season arcs and episode outlines append full plan revisions;
  spoken/visual approval binds to one revision, later edits make it stale, and
  approved/production episode plans reject mutation. Concurrent creation preserves
  ten unique, ordered episode numbers; v1 project backups remain importable.
- Commit `1de6cfb`, GitHub CI run `33274379025`: the macOS app exposes rename,
  archive/unarchive, archived-project filtering and native JSON backup/restore;
  16 Runtime tests, Swift tests, full application build and bundled-Runtime smoke passed.
- Commit `c38dc62`, GitHub CI run `33274544825`: the native app now edits season
  arcs and per-episode logline/outlines, displays current/stale plan approval and
  locked episode state, supports visual plan approval, and fails closed on child
  approval until the guardian-presence control is confirmed. Swift tests, full
  application build and bundled-Runtime smoke passed.
- Commit `9a70b08`, GitHub CI run `33275504662`: voice dictation edits season and
  episode plans while explicit voice confirmation binds approval to the current revision.
- Commit `c4d31ff`, GitHub CI run `33275631055`: every episode has an independent
  persisted-state-derived stage, percentage, current action, explanation and
  cancel/resume capability; the native episode strip and editor display that state.
- Still required before `PASS`: clean-account voice-only, accessibility and restart/import
  QA evidence on the same release candidate. Implementation alone is not acceptance.

## SOP-04 · Script creation, review and approval — IN_PROGRESS

Acceptance:

- Interview transcript becomes project bible, season plan and episode drafts.
- Script revisions retain provenance and approved narrative authority.
- Nalu can read a plain-language episode summary aloud.
- User corrections create a new revision without overwriting history.
- Production cannot start from an unapproved revision.

QA:

- Approval, revocation, stale revision and child guardian negative tests.
- Human review confirms the spoken summary matches the locked script.

Current evidence:

- Script revisions preserve content, plain-language voice summary, source transcript,
  narrative metadata and approval audit history; production rejects unapproved scripts.
- Commit `42d8cc4`, GitHub CI run `33275705267`: history listing, latest-revision-only
  approval, explicit revocation and revoked-script production blocking passed 18 Runtime
  tests, real HTTP smoke, Swift tests and the full bundled macOS build.
- Commit `301d14a`, GitHub CI run `33275921609`: the native workbench lists and
  compares immutable revisions, creates typed or dictated revisions, speaks the
  plain-language summary in Mandarin, permits only latest-revision approval,
  supports explicit visual/voice approval and revocation, and gates child approval
  on guardian presence. Swift tests, full app build and bundled-Runtime smoke passed.
- Still required before `PASS`: human spoken-summary fidelity QA and clean-account
  voice correction/approval evidence; implementation and synthesized playback alone
  do not satisfy the human acceptance criterion.

## SOP-05 · Media assets, consent and privacy — IN_PROGRESS

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

Current evidence:

- The packaged app uses the single local SQLite database
  `~/Library/Application Support/Nalu Voice Studio/nalu.sqlite3`; the Runtime is
  loopback-only and has no database sync or telemetry-upload path.
- `docs/LOCAL_DATA.md` defines the local database, working-data, Keychain and
  provider boundary. Project exports exclude secrets, validate format/digest/schema
  and cross-project references.
- Commit `1466be5`, GitHub CI run `33276434097`: schema migration v6, managed
  local byte import, file-name/path/MIME/size enforcement, consent receipts and
  revocation, immutable production dependencies, full privacy ZIP, and
  title-confirmed transactional project deletion passed 21 Runtime tests, real
  HTTP smoke, OpenAPI compatibility and full macOS build. Negative fixtures cover
  unauthorized biometrics, child consent, traversal, external local paths,
  dependency-protected deletion, secrets/SQLite exclusion and verified absence.
- Commit `ea647f8`, GitHub CI run `33276621169`: the native app imports supported
  local media through the security-scoped picker, requires explicit face/voice
  authorization and child guardian confirmation, scopes to the project or selected
  episode, shows/revokes consent, exports the privacy ZIP, and passed Swift tests,
  full application build and bundled-Runtime smoke.
- Still required before `PASS`: season-specific asset scope, native dependency and
  complete-project-deletion review UI, Keychain integration, local at-rest
  encryption decision/implementation, and human privacy/deletion QA on the same
  release candidate.

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
- Scheduled release discovery and a quarantined, rollback-safe upgrade process.
- Nalu production package materializes a clean Qingshan workspace.
- No product path depends on E40/E41-specific filenames or absolute user paths.
- SD2 Pro and MiniMax-H3 compile through separate adapters.
- Preflight invokes required Qingshan gates and stores machine-readable evidence.
- Durable transaction submitter is the only paid POST path.
- A versioned adapter registry routes creative formats by declared capabilities and
  fails closed when no production line matches.

QA:

- Offline contract fixtures pass without credentials or paid calls.
- Authorized sandbox generation binds transaction, task ID, result and credit receipt.
- Duplicate submission, stale package and model-policy conflicts fail closed.

Current evidence:

- Pinned upstream snapshot, capability checks, immutable Nalu package, clean
  per-run workspace materializer and SHA-256 preflight evidence.
- Qingshan `v2026.08.29.1` candidate diff was quarantined and promoted after its
  changed contract test passed; the pin now includes the upstream MIT license and
  durable-submit preservation of wardrobe, dialogue-cut and pose-transition gates.
- Daily release discovery, whole-tree/capability hash verification and the
  `docs/QINGSHAN_UPGRADE_SOP.md` promotion process continuously productize new
  upstream results without following a moving branch.
- Commit `fb7be81`, GitHub CI run `33273732021`: complete upstream file-set and
  changed-area Qingshan contract tests passed alongside Nalu Runtime and macOS QA.
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

## SOP-11 · macOS packaging, updates and operations — IN_PROGRESS

Acceptance:

- Runtime bundled and supervised by the macOS application.
- Signed, hardened and notarized universal application.
- First-run permissions, model/runtime setup and diagnostics.
- Safe automatic updates and data migrations.
- Backup, restore, disk-space warning and long-running background behavior.

QA:

- Clean installation on supported Apple Silicon macOS versions.
- Upgrade and rollback rehearsal with a populated multi-episode project.

Current evidence:

- One-command source build creates an application and zip containing a PyInstaller
  Runtime, pinned Qingshan resources and a native Runtime supervisor.
- CI launches the bundled executable against a clean Application Support data root
  and verifies the real loopback health endpoint before uploading the app artifact.
- Commit `fb7be81`, GitHub CI run `33273732021`: Swift tests, self-contained
  Runtime build, application build, bundled-Runtime smoke and artifact upload passed.
  Artifact `Nalu-Voice-Studio-macOS` is 22,164,755 bytes; downloaded zip SHA-256 is
  `b7b1fbe4ac16a78d7b8048b35ae4da05a7a75542758e795d3ff241656c7cfd63`.
- Still required before `PASS`: Developer ID signing, hardened runtime, notarized
  universal release, update channel, disk diagnostics and clean-Mac upgrade/rollback QA.

## SOP-12 · End-to-end release-candidate acceptance — TODO

Acceptance scenarios:

1. Older adult creates a personal autobiography using voice and personal photos.
2. Guardian and child create a fictional multi-episode story.
3. A 10-episode project preserves identity, voice and narrative state across episodes.
4. One episode fails generation, survives restart, resumes safely and passes QA.
5. Approved final media exports and publishes without duplicate paid calls.
6. Animation intent selects a capability-checked route; commercial intent with no
   approved adapter remains a useful project but cannot start production.
7. A spoken usability report is redacted, kept local by default and cannot change or
   release application code without the controlled review pipeline.

Completion evidence:

- All scenarios run from a clean signed installation.
- Costs, task IDs, receipts, QA reports and published IDs reconcile.
- No P0/P1 defects remain open.
- SOP-00 through SOP-11 and SOP-13 are revalidated on the same release commit.

## SOP-13 · Controlled product evolution — IN_PROGRESS

Acceptance:

- Users can report usability problems, bugs, corrections, preferences and missing
  features by voice or text without leaving the app.
- Local-only is the default; sharing requires explicit authorization and child
  feedback requires guardian approval.
- Raw voice, media, project content, credentials and unrestricted logs are never
  automatic feedback attachments.
- Safe comfort preferences are explicit, reversible and local.
- Product changes follow report → redaction → triage → tested change → human review
  → signed/notarized staged update → rollback.
- The application never claims a report is fixed until the signed installed release
  can be linked to its reviewed change.

QA:

- Redaction, local-only, guardian-negative and deletion/export tests.
- Prompt-injection and malicious-diagnostic fixtures cannot execute development or
  release operations.
- One report completes the governed pipeline through a signed test update and one
  deliberately bad update is rolled back.

Current evidence:

- Local SQLite feedback queue, voice/text native entry, explicit share flag, child
  guardian gate and deterministic redaction are implemented with Runtime tests.
- `docs/CONTROLLED_EVOLUTION.md` defines the trust boundary and release state machine.
- Still required before `PASS`: preference controls, authorized issue export, agent
  triage integration, signed staged updater and end-to-end improvement/rollback QA.
