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
- Memory cards support visible and spoken readback, correction, repeat and explicit
  revision-bound archive confirmation.

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
- Commit `a0aad4e`, GitHub CI run `33278236616`: the conversation now follows live
  transcription automatically, shows animated listening and Runtime state, creates a
  visible persisted draft project immediately, exposes a large media button, and applies
  reversible voice comfort commands. Swift tests, full app build and bundled smoke passed.
- Commit `2b90ce6`, GitHub CI run `33278702366`: memory cards can be read aloud,
  corrected by voice, re-read and explicitly confirmed against the reviewed revision.
  Runtime tests, Swift tests, full app build and bundled smoke passed.
- Commits `67c8179` and `69785f7`, GitHub CI run `33279727263`: conversational
  interruptions are answered without advancing or polluting the interview state; the
  answer is spoken and returns to the unfinished prompt. The native client now exposes
  a consent-gated WebRTC mode using an ephemeral client secret, `gpt-realtime-2.1`,
  low-eagerness semantic VAD, interruption, visible states and transcript events.
  Runtime tests, Swift tests, full app build and bundled smoke passed.
- Manual native QA on the CI artifact confirmed the visible natural-voice entry and
  fail-closed consent sheet: without a Keychain credential, the start action is disabled.
- Commit `f2f0c66`, GitHub CI run `33280429718`: the Realtime session now exposes one
  exact-schema local interview tool, returns its result through the documented function
  output event flow, rejects protected operations, ignores duplicate calls, shows a live
  elapsed-time/status strip, attempts short network recovery, offers explicit retry and
  enforces a user-selected 5/10/20-minute ceiling. Runtime tests, Swift tests, full app
  build, bundled smoke and downloadable artifact passed.
- Commits `07fba19` and `e4b6a52`, GitHub CI run `33280779469`: an active Realtime
  session now owns season, episode and script dictation without starting a competing
  local microphone. It reads the newly selected task, serializes overlapping responses,
  saves reversible revisions, and permits season/script approval only when that exact
  native confirmation task was visibly armed and its phrase/guardian gates pass. Swift
  tests, full app build, bundled Runtime smoke and downloadable artifact passed.
- Commit `c2001b4`, GitHub CI run `33286249745`: the main family-material control
  now opens the native file picker directly and exposes a plain-language accessibility
  hint; archive management is a separate secondary action. Accessibility-tree QA on
  the downloaded artifact verified the native `Open` panel, safe cancel/return and
  readable Runtime, microphone and project states. `docs/ACCESSIBILITY_QA.md` records
  the environment, exact evidence and remaining human matrix. Swift tests, the full
  application build, bundled-Runtime smoke, ZIP and artifact upload passed.
- Still required before `PASS`: authorized paid Realtime connectivity, interruption,
  real function-call, network-loss, session-expiry and provider usage/cost QA;
  VoiceOver/Accessibility Inspector audit; and a clean-account voice-only QA session
  with real permissions.

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
- Voice intent distinguishes short drama, documentary, animation and commercial
  projects without silently routing an unsupported format to a paid production adapter.

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
- Commits `07fba19` and `e4b6a52`, GitHub CI run `33280779469`: the same live WebRTC
  session can receive season and episode plan revisions and an explicitly armed plan
  approval without opening a second microphone; protected task state and guardian gates
  remain native.
- Commit `c4d31ff`, GitHub CI run `33275631055`: every episode has an independent
  persisted-state-derived stage, percentage, current action, explanation and
  cancel/resume capability; the native episode strip and editor display that state.
- Commits `54df37d`, `d26b73e`, `0ec2bff` and `de22586`, GitHub CI runs
  `33284069716`, `33284236090` and `33284471023`: natural voice requests now create
  archive-led or archive-plus-reenactment documentary projects, display units as
  chapters, keep the production route `unassigned`, expose a local evidence-readiness
  gate and show/read its next step in the native asset workflow. CI passed 36 Runtime
  tests, 27 Swift tests, the complete app build, bundled-Runtime smoke and artifact
  upload. A real artifact accessibility-tree check confirmed the documentary project
  row reads “纪录片系列 · 计划 6 章”; the temporary QA project was then verified deleted.
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
- Commits `07fba19` and `e4b6a52`, GitHub CI run `33280779469`: Realtime speech can
  create an immutable script revision and complete an explicitly armed script approval;
  unarmed approval cannot route to the approval API and overlapping spoken prompts are
  serialized.
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
- Photos and scanned handwriting create local, provenance-linked memory cards; OCR
  drafts cannot become narrative authority without explicit confirmation.

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
- Commit `2b90ce6`, GitHub CI run `33278702366`: schema migration v10 adds local
  versioned family-memory cards, evidence links, revision-bound confirmation records,
  project export/restore and cascade deletion. The native app runs Apple Vision OCR
  locally, reads cards aloud, accepts typed/voice corrections and requires re-review
  after every edit. Cross-project evidence and stale confirmation fail closed in tests.
- Commit `0a12ec1`, GitHub CI run `33278834223`: the native picker accepts scanned
  handwriting as an image source. Commit `67c8179` moves the oversized inline form to
  a dedicated scrollable sheet and replaces it with a prominent guided upload card.
- Commits `0ec2bff` and `de22586`, GitHub CI runs `33284236090` and `33284471023`:
  documentary readiness distinguishes unlinked, draft, confirmed and narratively
  authorized local evidence. A confirmed `reference_only` card cannot become factual
  authority, and biometric visual-generation authority disappears immediately after
  consent revocation. The macOS client refreshes and can read this state aloud.
- Commits `6ffe814` and `1a7822a`, GitHub CI run `33285285247`: the default family-
  material flow is now a single prominent file choice instead of a required metadata
  form. Nalu safely infers local archive type, draft name, project scope and
  `reference_only` use, then asks one short voice question at a time for event, date,
  place and significance before reading the memory card back for explicit archive
  confirmation. Audio/video archives remain distinct from biometric generation
  references; face/voice generation consent is never inferred. All 37 Runtime tests,
  Swift tests, full application build, bundled-Runtime smoke, ZIP and artifact upload
  passed. The professional editor remains available only behind an advanced disclosure.
- Commit `c2001b4`, GitHub CI run `33286249745`: both prominent family-material
  controls bypass the manager and open the native file picker immediately; the manager
  remains a secondary entry for existing assets and professional authorization. Artifact
  accessibility-tree QA verified the direct panel and safe cancel without selecting or
  transmitting a file. The single QA-created empty project was deleted and the Runtime
  reported `verified_absent: true`.
- Still required before `PASS`: human privacy/deletion QA and clean-account OCR,
  correction and voice archive QA on the same signed release candidate. Automated
  Computer Use crashed while opening the new asset sheet, while Nalu stayed running,
  so that visual sheet check remains explicitly unaccepted.

## SOP-06 · Cross-episode inheritance and continuity — IN_PROGRESS

Acceptance:

- Project libraries for characters, scenes, props, voices and styles.
- A local family-memory graph links people, relationships, places, dates, events and
  source evidence; only confirmed revisions are narrative authority.
- Immutable resolved-asset snapshot per production run.
- Episode end-state captures wardrobe, location, injuries, prop ownership,
  relationships, revealed facts, time/weather and unresolved hooks.
- Next-episode preflight rejects unexplained continuity conflicts.
- Explicit, versioned override path with user review.

QA:

- At least three multi-episode continuity fixtures with positive and negative cases.
- Regression verifies completed episodes do not change after library edits.

Current evidence:

- Commit `2b90ce6`, GitHub CI run `33278702366`: structured people, date, place,
  relevance and permitted-use fields are bound to local source assets with immutable
  revisions and confirmation audit. `docs/FAMILY_MEMORY_LIBRARY.md` defines the
  provenance and conflict boundary.
- Commit `4f772e4`, GitHub CI run `33281856388`: typed episode end state covers
  character location, wardrobe, injuries, held props, relationships and revealed
  facts; prop owner/location/condition; scene, time, weather and unresolved hooks.
  A pure preflight blocks missing or unexplained inherited fields before workspace
  or paid submission. Exact transition explanations and a versioned, reviewed,
  explicit-confirmation override are bound to the immutable approved script and
  production package. Four multi-episode test cases cover a matching handoff,
  character/prop/time conflicts, explained transitions, mismatched and exact
  overrides, missing opening declarations and empty-state bypass attempts.
- Commits `c8ad29e` and `91e3e64`, GitHub CI run `33283238515`: the native macOS
  client reads the prior handoff, keeps opening and ending forms separate, supports
  multiple typed characters and props, reads both states aloud, displays plain-language
  conflicts, records explanations, protects the advanced override with explicit review,
  and locks the accepted preflight into the next script revision. Swift tests, the full
  app build, bundled Runtime smoke, ZIP and downloadable artifact passed.
- Commit `ed1080f`, GitHub CI run `33283577897`: schema migration v11 adds
  project-level character, scene, prop, voice and style entities with stable identity,
  append-only revisions and explicit current-revision confirmation. Only confirmed
  revisions resolve into immutable production packages and typed Qingshan library
  indexes. Tests cover all five kinds, duplicate identity, ambiguous/stale confirmation,
  v7 backup/restore, revision history, future-run updates and byte-for-byte immutability
  of an earlier episode package. All 33 Runtime tests, real HTTP smoke, OpenAPI gates,
  Swift tests, full app build, bundle smoke and downloadable artifact passed.
- Commit `4b79580`, GitHub CI run `33283727474`: confirmed library aliases add a
  fail-closed first entity-resolution gate. Spoken names resolve only against confirmed
  revisions; unknown mentions return not-found, while colliding names or aliases block
  the second entity's confirmation. All 34 Runtime tests, OpenAPI compatibility, real
  HTTP smoke, Swift tests, full app build, bundle smoke and artifact upload passed.
- Commits `21c09a0` and `23dc463`, GitHub CI run `33286805948`: the native client
  lists, reads and creates project-level character, scene, prop, voice and style drafts
  before season/episode planning exists. A two-question local voice flow reads the draft
  back and requires a separate explicit confirmation turn; ambiguous or negative speech
  leaves it excluded from production. Swift contract tests, full build, bundle smoke,
  ZIP and artifact upload passed. Artifact accessibility-tree QA verified the expanded
  editor and all five native voice-menu actions without creating data or requesting
  microphone permission.
- Commit `396d224`, GitHub CI run `33287357769`: a fail-closed family-memory graph
  preflight blocks incompatible storyteller relationships and specifically named event
  dates or places before confirmation. Every conflict binds both memory-card IDs, exact
  revisions and managed asset IDs; the native client keeps the card as a draft, displays
  a plain-language red state and reads the discrepancy aloud. Five Runtime fixtures cover
  relationship, date and place failures plus compatible approximate dates, aliases,
  drafts, reference-only authority and generic-photo false-positive boundaries. All 42
  Runtime tests, OpenAPI compatibility, real HTTP smoke, Swift contract tests, full app
  build, bundled Runtime smoke, ZIP and downloadable artifact passed. A same-turn native
  accessibility-tree recheck could not run because the QA Mac was locked, so no human or
  AX pass is claimed from that attempt.
- Commits `01065bc` and `b571e83`, GitHub CI run `33293222020`: the Runtime now
  prepares a script-revision-bound, non-authoritative ending-state proposal from locked
  structured metadata or explicit ending markers and refuses unapproved, empty, stale,
  duplicate or ambiguous confirmation. The native macOS flow auto-fills the typed state,
  keeps the manual form behind an advanced disclosure, reads every character, prop,
  place, time, weather and unresolved-hook field, and unlocks confirmation only after
  uninterrupted speech completion. Cancellation, another utterance or any edit invalidates
  review; edited facts require a persisted change summary. A dedicated SQLite migration
  records proposal hash, reviewed script/content, review channel, guardian state and change
  summary, and project export v8 restores that immutable audit with the handoff snapshot.
  Five Runtime fixtures plus Swift model/voice-flow tests cover inheritance, markers,
  stale/duplicate review, child guardian protection, edited readback, cancellation and
  ambiguous speech. All 47 Runtime tests, Swift tests, full app build, bundled-Runtime
  smoke, ZIP and downloadable artifact passed.
- Commit `ea74935`, GitHub CI run `33293652398`: every unresolved hook from the exact
  inherited snapshot now requires a versioned `carry_forward`, `resolved` or `abandoned`
  decision; resolved and abandoned hooks require an explanation and the complete set
  requires explicit confirmation. Missing, stale, incomplete, duplicate or ambiguous
  review fails closed, and child projects require guardian presence. The same contract
  runs in the preview endpoint, before production and when confirming the ending:
  carried hooks must remain, while resolved or abandoned hooks must be absent. The
  approved script and immutable production package retain the reviewed dispositions.
  The native macOS client can ask one hook at a time by voice, request the closure reason,
  read the complete arrangement back and require a separate explicit confirmation; edits
  invalidate that confirmation. All 51 Runtime tests, Swift voice/model tests, full app
  build, bundled-Runtime smoke, ZIP and downloadable artifact passed.
- Commits `0403d26`, `b933c25` and `1d80d99`, GitHub CI run `33297505140`:
  approved unstructured legacy scripts now have a conservative, deterministic local
  final-scene extraction path for time, weather, named-character location, wardrobe,
  injury, held props, learned facts and explicit unresolved hooks. Earlier scenes,
  uncertain prose and ordinary dialogue questions are excluded. Every semantic result
  carries its exact approved-script excerpt, extraction rule and confidence; the native
  app shows that evidence without requiring a professional form, while the existing
  complete readback and separate confirmation remain authoritative. Runtime fixtures
  cover evidence binding, final-scene isolation, ambiguous negative cases and confirmed
  snapshot creation. All 53 Runtime tests, OpenAPI compatibility, real HTTP smoke, Swift
  tests including old-response compatibility, full app build, bundled-Runtime smoke, ZIP
  and downloadable artifact passed.
- Commit `1115155`, GitHub CI run `33297766372`: QA-stage rendered outputs can now be
  sealed to the exact production-package digest, confirmed project-library snapshot,
  Qingshan workspace manifest and per-file byte size/SHA-256. Paths outside the managed
  exports directory, symbolic links, empty files, duplicate paths, missing masters,
  altered packages and duplicate seals fail closed. A regression changes and confirms
  the character library after sealing, proves that the earlier package and master remain
  byte-for-byte unchanged, then mutates the master and verifies that integrity becomes
  false with the exact failed path. All 55 Runtime tests, OpenAPI compatibility, real HTTP
  smoke, Swift tests, full app build, bundled-Runtime smoke, ZIP and downloadable artifact
  passed. The seal deliberately does not make an episode publishable by itself.
- Commit `c7c4795`, GitHub CI run `33297985886`: production completion now requires a
  still-valid output seal with one master and captions plus one sealed structured human
  QA report bound to that run and master hash. Original-resolution picture, audio sync,
  captions, continuity and safety checks must all pass; completion requires explicit
  confirmation and child projects require guardian approval. The run `qa_review →
  completed` and episode `qa_review → ready_to_publish` updates and both audit events share
  one SQLite transaction. A failpoint after all updates but before commit proves complete
  rollback, followed by a safe same-seal retry and duplicate-event protection. The
  regression then changes the project character library after the episode is completed
  and verifies the earlier master, package and seal remain unchanged. All 57 Runtime
  tests, OpenAPI compatibility, real HTTP smoke, Swift tests, full app build, bundled-
  Runtime smoke, ZIP and downloadable artifact passed. The automated human-QA JSON is a
  format fixture and is not claimed as actual human review.
- Still required before `PASS`: human/accessibility QA of the native continuity workflow
  on the same release candidate.

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
- Commit `a0aad4e`, GitHub CI run `33278236616`: the feedback queue, native voice/text
  entry and local reversible comfort preferences passed Runtime and Swift tests, full
  macOS build and bundled-Runtime smoke.
- `docs/CONTROLLED_EVOLUTION.md` defines the trust boundary and release state machine.
- Still required before `PASS`: preference controls, authorized issue export, agent
  triage integration, signed staged updater and end-to-end improvement/rollback QA.
