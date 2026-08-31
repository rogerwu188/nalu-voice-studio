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
- Commit `3772426`, GitHub CI run `33326138549`: schema migration v14 preserves
  existing data and adds digest-bound feedback-review bundles; project export v9 restores
  them while retaining v1-v8 import compatibility. All 69 Runtime tests, OpenAPI
  freshness/backward compatibility, real HTTP smoke and the complete macOS build passed.

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

## SOP-06 · Cross-episode inheritance and continuity — PASS

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
- GitHub issue `#4` records native accessibility E2E on the downloadable artifact from
  the same `c7c4795` release candidate, including ZIP and executable SHA-256. Against an
  isolated temporary Runtime, the accessibility tree exposed the automatic extraction,
  11 exact source-evidence entries and every populated continuity field. Confirmation was
  disabled before and during complete speech playback, enabled only after uninterrupted
  completion, then immediately disabled again after changing weather from 大雪 to 小雪;
  the required change-summary field appeared. No microphone, paid generation, release
  action or user project data was used. This closes the SOP-06 native accessibility gate
  without claiming acoustic voice-quality review or whole-product completion.
- Completion audit on release candidate `8be9945`: implementation regressions and the
  full macOS build passed in GitHub CI run `33300671992`, but the then-current native
  accessibility E2E evidence was bound to an earlier artifact, so SOP-06 was correctly
  downgraded to `REGRESSION` until the scenario could be rerun.
- Product commit `ac100b5`, GitHub CI run `33327724626`, release rehearsal
  `33327906350` and the current revalidation comment on GitHub issue `#4`: the downloaded
  universal `0.1.0-rc1 (1001)` artifact, ZIP SHA-256
  `e541a44970d54496562dff950dfb2d201967ab6bc404eecbaf4b068f79b16182`, was launched
  against a new isolated Runtime. Its native accessibility tree exposed all 11 semantic
  source-evidence entries and every populated handoff field. Confirmation stayed disabled
  before and during complete readback, enabled after uninterrupted completion, and was
  invalidated immediately when weather changed from 大雪 to 小雪. The required change
  summary appeared; after a second complete readback, native confirmation saved one
  immutable snapshot whose Runtime response retained 小雪, 杭州旧火车站 and both unresolved
  hooks. No user project, microphone, provider credential, paid generation or release
  account was used. Evidence:
  `https://github.com/rogerwu188/nalu-voice-studio/issues/4#issuecomment-5471990419`.
- Evidence commit `8be5bdb`, GitHub CI run `33342602904`: the repository now persists
  the `/goal` checkpoint and next safe action in `docs/GOAL_PROGRESS.json`, audits that
  state against this SOP in CI, rejects false completion and unsafe pause/idempotency
  policy changes, and passed 81 Runtime tests, real HTTP smoke, both native Swift suites,
  both architecture builds/smokes and the universal merge/smoke. This records the closed
  regression without promoting the whole product to complete.

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
- SD2 Pro and MiniMax-H3 now compile through separate versioned local adapters. Each
  produces a model-specific, digest-bound contract with its actual native resolution,
  duration, reference-transport and identity constraints; package, compilation and
  workspace bindings are revalidated during preflight. Local compilation explicitly
  remains unable to authorize a paid submission. Runtime regressions cover both routes,
  compiler separation, package tampering and compilation tampering.
- Commit `654c672`, GitHub CI run `33298709262`: all 61 Runtime tests, upstream pin and
  OpenAPI checks, real HTTP smoke, Swift tests, full application build, bundled-Runtime
  smoke, ZIP and artifact upload passed for the separate compiler contracts.
- Qingshan's own registry-integrity tool currently finds 68 registered gates and 65/65
  coded gates runtime-bound, but release `v2026.08.29.1` omits eight declared evidence
  paths and contains one host-specific absolute test path, so it cannot run the complete
  registered test set portably. Upstream issue `#20`
  records the exact release defect. Nalu binds that quarantine to the upstream commit,
  registry SHA and exact failure list in every workspace; new drift fails preflight and
  the known quarantine blocks paid execution while permitting evidence-rich local dry
  runs. This is not recorded as a full gate pass.
- Commits `700c239`, `1654b76` and `1a2582a`, GitHub CI runs `33326751267` and
  `33326931637`: the Runtime binds exactly one durable submitter; Repository remote-task
  writes require its per-instance authority, and the only Runtime source allowed to
  invoke a paid transport is that submitter. Immediately before I/O it revalidates the
  immutable package hash, explicit approver, requested model and provider idempotency
  guarantee. Concrete paid transports remain deliberately unregistered.
- Still required before `PASS`: a corrected pinned Qingshan release whose registry
  integrity and complete registered tests pass, plus authorized real-provider sandbox
  task/result/receipt evidence. Offline authority and transport doubles are not a paid
  generation claim.

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
- SQLite migration 13 adds immutable per-run remote-task intents and provider task/result/
  receipt bindings. Dry runs cannot create them; changed fingerprints, changed provider
  task identity and duplicate provider task IDs fail closed. Prepared, submitted,
  ambiguous-charge, verified-zero-charge, completed and cancelled states are explicit.
- A failpoint after a remote binding update but before its ordered run event proves the
  whole SQLite transaction rolls back. The same evidence then commits once, survives a
  complete Runtime restart and replays idempotently. Separate regressions cover ambiguous
  responses, exact zero-charge reconciliation and duplicate remote task protection. This
  is offline persistence evidence and does not claim a provider call occurred.
- Commit `630dcaa`, GitHub CI run `33299221573`: all 64 Runtime tests, Qingshan pin and
  OpenAPI checks, real HTTP smoke, Swift tests, full application build, bundled-Runtime
  smoke, ZIP and downloadable artifact passed. The same run confirms gate-registry
  quarantine behavior is deterministic on clean Linux and macOS hosts.
- Episode progress now derives finer stages from durable remote bindings: locally
  prepared, provider accepted, ambiguous charge under reconciliation, verified
  zero-charge awaiting new approval, and remote results received. The ambiguous-charge
  state explicitly disables cancellation and says that Nalu will not auto-resubmit.
- Commit `f36a8f0`, GitHub CI run `33299566385`: Runtime, OpenAPI compatibility, real
  HTTP smoke, Swift tests, full app build, bundled-Runtime smoke and artifact upload all
  passed for durable task-derived stage explanations.
- The native client now refreshes every episode's durable production state every four
  seconds instead of only when a project is opened. A prominent card uses a moving arrow
  only for actual work, and separately explains waiting-for-confirmation, ambiguous
  charge, safely stopped and completed states. Transient refresh failure is visible and
  retried without discarding the last durable state.
- Safe pause and preflight-only resume are wired to the Runtime. Button pause requires a
  visible confirmation. Voice pause requires the specific “pause this episode's
  production” intent and a second explicit confirmation; bare “pause” remains an
  interview command. Ambiguous-charge state exposes no pause control, and resume never
  skips the paid preflight approval boundary.
- Commit `3449e14`, GitHub CI run `33300330314`: Swift presentation and voice-command
  regressions, Runtime/OpenAPI checks, full application build, bundled-Runtime smoke, ZIP
  and artifact upload all passed. This is automated state/interaction evidence and does
  not replace a signed-app long-running human production session.
- Commits `700c239`, `1654b76` and `1a2582a`, GitHub CI runs `33326751267` and
  `33326931637`: direct public Repository mutation entry points were removed; one
  application-wide submitter owns the guarded write authority and paid transport call.
  Offline doubles prove provider acceptance followed by a pre-commit crash reuses the
  exact provider idempotency key after restart and records one charge, while an ambiguous
  timeout is quarantined and never automatically reposted. Changed requests, fabricated
  authority, duplicate binding, missing package approval, package tampering, provider
  mismatch and transports without idempotency fail before I/O. All 77 Runtime tests,
  real HTTP smoke, OpenAPI gates, Swift tests, full macOS build, bundled-Runtime smoke,
  release verification and artifact upload passed. No provider network call occurred.
- Still required before `PASS`: run authorized provider crash tests at every real
  network/charge/ledger boundary, reconcile real ambiguous charges against the provider
  and validate the stage explanations in a signed-app long-running production QA session.

## SOP-09 · Postproduction and release-blocking QA — IN_PROGRESS

Acceptance:

- Shot selection, normalized media, dialogue, ambience, foley, music and subtitles.
- Final MP4 normalization and timestamp checks.
- Identity, wardrobe, space/axis, pose, prop, sound and transition QA evidence.
- ASR/VAD, subtitle, frame-repeat and media-boundary checks.
- Failed gates produce specific repair tasks and cannot be bypassed silently.

QA:

- Golden media fixtures for pass/fail cases.
- Human audiovisual review of original-resolution final master.

Current evidence:

- Rendered-output seals bind the exact master/captions/QA artifacts to the immutable
  production package, confirmed project-library snapshot and Qingshan workspace; file,
  package and workspace mutation fail closed.
- Completion requires one sealed master, captions and structured original-resolution
  human review whose picture, audio sync, captions, continuity and safety checks all pass.
  Run and episode completion plus audit events share one crash-safe SQLite transaction.
- Failed completion now persists a digest-bound, restart-readable repair plan with
  specific release-blocking tasks for missing artifacts, evidence binding, picture,
  audio, captions, continuity, safety and original-resolution review. Identical failed
  evidence is idempotent and never advances the run beyond `qa_review`.
- Commit `ad57e32`, GitHub CI run `33299440973`: all 65 Runtime tests, OpenAPI
  compatibility, real HTTP smoke, Swift tests, application build, bundled-Runtime smoke,
  ZIP and artifact upload passed for the release-blocking repair-plan contract.
- A deterministic sealed-file gate now validates MP4 box integrity, `ftyp`/`moov`/`mdat`,
  fast-start order and positive movie-header duration plus UTF-8 WebVTT cue syntax,
  ordering, overlap and master-duration boundaries. Pass/fail structural fixtures prove
  specific `mp4_structure` and `caption_timeline` repair tasks. This is structural QA and
  is not misreported as decoded picture/audio acceptance.
- Commit `5177fa5`, GitHub CI run `33299757668`: all 66 Runtime tests, OpenAPI
  compatibility, real HTTP smoke, Swift tests, full app build, bundled-Runtime smoke,
  ZIP and artifact upload passed for MP4/container and caption-timeline structural QA.
- The current checkpoint decodes the exact sealed MP4 with PyAV/FFmpeg and measures every
  picture frame plus normalized 16 kHz mono audio. It fails closed on undecodable or
  missing streams, unstable dimensions/timestamps, excessive repeated or black frames,
  insufficient voice activity, long silence, clipping and WebVTT cues that do not
  overlap voiced intervals. Playable AAC/MP4 pass fixtures and frozen-picture/silent-
  audio failure fixtures prove the release-blocking report, exact-seal binding,
  idempotent replay and specific repair tasks. Production completion and offline release
  packaging now require both structural and decoded reports to PASS.
- This implementation intentionally records `semantic_asr_verified: false`: VAD and cue
  overlap are not transcript correctness, lip sync, shot-aware adjacent-shot continuity
  or human review.
- Commits `f224356` and `d23c7b9`, GitHub CI run `33343613892`: all 82 Runtime tests,
  OpenAPI backward compatibility, SOP/progress audits and real HTTP smoke passed. The
  same commit built, verified and launched the PyAV/FFmpeg-equipped packaged Runtime on
  Apple Silicon and Intel, then merged, verified and launched the universal application.
- The current checkpoint adds an explicit Qingshan workspace output contract for an
  immutable, production-package-bound shot manifest. Runtime compares visible WebVTT
  dialogue with timed local ASR segments, decodes both sides of each authored cut,
  validates transition-contract digests and blocks completion/release packaging unless
  the report passes against the same seal. The native QA-stage action downloads and
  digest-verifies the sealed master, requires Apple on-device `zh-CN` recognition and
  never silently falls back to cloud recognition. Automated playable pass/fail fixtures
  cover semantic mismatch, corrupt transition evidence and immutable replay.
- Commit `c3dbba1`, GitHub CI run `33345468515`: all 84 Runtime tests, OpenAPI backward
  compatibility, SOP/progress audits and real HTTP smoke passed. The same exact commit
  passed Swift tests and produced independently launched Apple Silicon and Intel bundles,
  followed by a verified universal application and bundled Runtime. Packaged-artifact QA
  on ZIP SHA-256 `8524df138c1dfaf3a9826cbe9087a45f2bc1c2126b676d3a8ce973b1b45e0153`
  exposed “检查成片声音与转场” as a native accessibility action with the local-only and
  human-review warning. A deliberately unsealed QA run failed before recognition and
  visibly reported that no cloud recognition or release occurred; no microphone
  permission, provider credential or paid call was used. The exact temporary project and
  its one production run were then deleted with `verified_absent: true`.
- Commit `b81bd6e` implements the next postproduction checkpoint. Every production
  workspace now declares an immutable, package-bound
  `postproduction_manifest`. The local Runtime decodes the selected source and normalized
  segments, rejects unadmitted shots, unsafe paths, digest drift, non-contiguous edits,
  non-zero timestamps and mismatched frame/audio formats. It requires explicit dialogue,
  ambience, foley, music and SFX dispositions, verifies included 48 kHz stereo stems and
  their cue provenance, fingerprints the published mix, compares its decoded energy to
  the sealed master's audio, and binds the exact WebVTT captions and source contract.
  Failures create specific release-blocking shot-selection, normalization, stem, mix or
  subtitle repair tasks. Completion and offline release packaging now require the same-
  seal lineage report to PASS. Five real decoded WAV stems, source/normalized MP4 copies,
  published-mix/master binding and an unadmitted-shot negative fixture are covered by the
  85-test suite. GitHub CI run `33347500981` passed Runtime, OpenAPI, Swift, independent
  Apple Silicon and Intel application builds, both bundled smokes and the universal merge.
  Packaged-Runtime QA used universal artifact `9742534531`, ZIP SHA-256
  `7d5769acc5e3b6a7aaa8ec7cdebd02e76305d00afa3329af9150dc6d84c15d9d`, and
  decoded the complete source/normalized/stem/mix/caption pass fixture through the
  bundled executable. It emitted `nalu.postproduction-lineage-output-contract/v1` with
  all five required audio layers and exact published-mix/subtitle binding. The unsealed
  negative run returned HTTP 409 instead of manufacturing lineage evidence. No provider,
  credential, paid generation or publication was used. The unchanged Runtime suite was
  revalidated in release-candidate CI run `33349286197` after the native supervisor
  lifecycle repairs. This closes the automated lineage checkpoint, not SOP-09.
- Commit `9b7bd45` adds an immutable same-seal visual-continuity gate. The Runtime
  re-decodes the exact sealed master and independently verifies evidence-frame digests,
  shot time ranges, the frozen production package and the confirmed library revision.
  Identity, wardrobe, space/axis, pose and props have fixed confidence thresholds and
  separate release-blocking repair codes; a producer-authored `PASS` flag is not trusted.
  Completion and offline release packaging now require this report to pass against the
  same output seal. GitHub CI run `33350559526` passed 86 Runtime tests, OpenAPI and
  progress audits, real HTTP smoke, Swift tests, independent arm64/x86_64 builds and
  smokes, and universal job `99363729575`.
- The exact universal artifact `9743544705`, ZIP SHA-256
  `eeb917b9cb0931d2ea0dfd6fbd1f7998fe6bf215e04c73f3e0fd9bf04ea0fc30`, passed the
  repository's universal release verifier; both the native executable and bundled
  Runtime contained arm64 and x86_64 slices. On macOS, the bundled Runtime SHA-256
  `c0b143c9247e4aabfd4f78a1b47cb164681cf900211537d83e06669bcc704961` ran against an
  isolated temporary SQLite database. A real HTTP pass fixture decoded 20 frames and
  passed all five domains. A wardrobe mismatch produced only `visual_wardrobe`; a
  fabricated evidence-frame digest failed every domain and produced the manifest plus
  five domain-specific repair tasks. Stored GET reports exactly replayed their initial
  results, the temporary Runtime stopped cleanly, and port 8765 disappeared. No provider,
  credential, paid generation or publication was used. The Mac was locked when the
  native-window startup/quit repetition was attempted, so no new GUI or accessibility
  acceptance is inferred from this checkpoint. The prior universal lifecycle evidence
  remains valid only for commit `d285aa9`.
- This gate validates immutable analyzer provenance and its claims against package,
  library, timeline and decoded-frame evidence. It does not yet execute a perceptual
  vision model and is not evidence that an actual actor, garment or prop looks correct.
- Commit `eb69f27` moves postproduction execution inside the local Runtime. A bounded,
  hash-addressed plan now binds every admitted provider segment and receipt, explicit
  source in/out points, the five required audio sources and cue digests, captions and
  the target timeline. The Runtime decodes and trims the source video, writes normalized
  zero-based segments, normalizes dialogue/ambience/foley/music/SFX to 48 kHz stereo,
  applies explicit gains, renders the published mix and final MP4, rehashes every source,
  writes execution-derived lineage and atomically exposes the result. Identical retries
  replay exactly; changed plans, path traversal, missing layers, pre-render digest drift,
  post-render source mutation and a simulated filesystem/SQLite commit interruption fail
  closed or recover without duplicate state events. The 88-test suite, real HTTP smoke,
  OpenAPI compatibility and SOP/progress audits passed in GitHub CI run `33352196081`,
  together with independent arm64 job `99367586208`, x86_64 job `99367586351` and
  universal job `99368323647`.
- The exact universal artifact `9744074571` (GitHub artifact digest
  `60fa7573fa0f5a4d5e9e53496328ae9619dd593953a98903f2a711526f4fd39b`) had ZIP SHA-256
  `4d159cd6d5564c559e92c6221dcce26022121c152322c9835a7c351792479397` and passed the
  repository universal verifier. Its main executable SHA-256
  `f7a1d18f5e3c1aada87eac6b25bc7d55cd7d89b6b2d1a459e8d083ebb3657a91` and bundled
  Runtime SHA-256 `544f16f04b14246143edad8371c336a9afb174415f01a7b9d8bab88119d8537b`
  both contained arm64 and x86_64 slices. The reusable
  `scripts/qa-packaged-postproduction.py` harness started that exact bundled Runtime
  against an isolated SQLite database and exercised the endpoint over real loopback
  HTTP. It materialized two ordered shots and all five non-silent stems, sealed the
  generated master/captions/lineage manifest, replayed the same plan without a second
  event, rejected a changed plan, and passed decoded lineage QA. A second run with a
  false source SHA returned HTTP 409, remained `running`/`postproduction` and left zero
  accepted results. The Runtime then stopped and port 8765 closed. The evidence report
  has SHA-256 `a81c55fe8199a54b0a343caa8297facfda2ebd238951d982414cd06d8943500a`.
  No provider, credential, paid generation, non-loopback network or publication call was
  used. The bundle is still ad-hoc signed, so this is not Developer ID/notarization
  evidence.
- Commit `3a31419` replaces whole-episode decoded arrays and the episode-length
  floating-point mix accumulator with fixed 8,192-sample stereo generators. Source
  trimming, normalized-segment audio, five stem writes, gain application, published-mix
  rendering and final-master AAC input now remain chunked. A 90-second PCM fixture
  consumes every sample while enforcing the fixed block ceiling and a Python heap peak
  below 4 MiB. This makes Python memory independent of episode length; it does not claim
  a full-process RSS or device-performance result for a 30-minute master. GitHub CI run
  `33353565965` passed all 89 Runtime tests, real HTTP smoke, OpenAPI and progress audits,
  arm64 job `99371350910`, x86_64 job `99371351101` and universal job `99371980750`.
- The exact universal artifact `9744466324` (GitHub artifact digest
  `8d14dae99b63d35531a6dfe85791d19dc0b06e61c3b72b86d8c8f71a2ac15c8e`) had ZIP SHA-256
  `89106461a48380b06d740cf27519ad47f001aabbef5fac3e3df2856767372cf1`.
  Its main executable SHA-256 was
  `b374df73210e38a7900591a1a5abd06616eb01a98b7a729826fa9ce39d98c8ae` and bundled
  Runtime SHA-256 was `7c4005b77de4565a8ef02cba45075fbccfac7271e01c7682bce1d1b985e88206`;
  both were universal. The packaged-Runtime harness repeated the two-shot/five-stem
  materialization, exact replay, changed-plan rejection, seal and decoded lineage PASS.
  Its digest-drift case returned 409, retained `running`/`postproduction` and accepted no
  result. The Runtime stopped and port 8765 closed. The evidence report has SHA-256
  `cd329277fa7e40235c364ce4f1988e1db4891d4ec778bd9dee801f0e9c969b18`.
  No provider, credential, paid generation, non-loopback network or publication call was
  used; the bundle remains ad-hoc signed.
- Commit `17b242f` freezes the local visual analyzer's non-sensitive input authority.
  Each workspace now maps consented character and prop references to confirmed stable
  names or aliases, rebinds their managed-file SHA-256 and scope, and records the exact
  confirmed entity revision plus expected identity, wardrobe, screen axis, pose and held
  props. Unknown or ambiguous reference subjects, missing/invalid image digests, absent
  character references, incomplete target fields, unconfirmed held props and missing prop
  references make readiness `BLOCKED`. The contract is local-only, forbids provider
  upload, requires source rehash before analysis and explicitly rejects authored
  observations as perceptual evidence. GitHub CI run `33354670668` passed all 91 Runtime
  tests, real HTTP smoke, OpenAPI/SOP/progress gates, both Swift suites, independent arm64
  job `99374431315`, x86_64 job `99374431334` and universal job `99374946162`.
- Exact universal artifact `9744795797` (GitHub artifact digest
  `1fc99f6416d1ceb2470e6156d20e319cd31df7541225877d900a8e9179cd33b1`) had ZIP
  SHA-256 `fd4d6ea8b5f9827441c2d91cb43d970e12e214cf727043d0795eb359b4ee1405`.
  Its main executable SHA-256 was
  `4cada116c85c8be0ff4c8add51c47ed960de156a5e6373b598e04944dfd834c2` and bundled
  Runtime SHA-256 was `64aa3d43894cf63d35854c6cbf9b889f500086ef47ac846a29100d311146da07`;
  both contained arm64 and x86_64 slices and the app's ad-hoc signature verified. The
  reusable `scripts/qa-packaged-visual-inputs.py` harness started that exact bundled
  Runtime on an isolated SQLite database and real loopback HTTP. Its positive project
  bound one confirmed character, one confirmed prop and two rehashed managed references
  to a `READY` input digest with provider upload disabled. Its negative project omitted
  the held-prop authority and produced only `HELD_PROP_AUTHORITY_MISSING` with readiness
  `BLOCKED`. The Runtime stopped and port 8765 closed. The evidence report file has
  SHA-256 `7b972eb2202e588ef8be838141e81ed2bb81c6fc92fb4dbd8fb7dc1c20422d45`.
  No provider, credential, paid generation, non-loopback network or publication call was
  used; no perceptual recognition or human visual acceptance is claimed.
- Commits `e7297b0` and `1da3e63` add and package the first real local perceptual
  executor. The Runtime rehashes the exact confirmed character/prop references and
  materialized master, decodes each authored shot midpoint with PyAV, and invokes a
  separately hashed universal Swift executable. That executable uses Apple Vision image
  feature prints, body pose, face and attention saliency plus Core Image area colour to
  derive machine measurements for identity, wardrobe, screen axis, pose and props. The
  Runtime maps those measurements into the immutable five-domain manifest; malformed,
  non-finite, low-confidence, drifted or producer-uploaded evidence fails closed. Exact
  replay and the filesystem/SQLite recovery boundary retain one visual-analysis event.
- GitHub CI run `33357165343` passed all 92 Runtime tests, real HTTP smoke,
  OpenAPI/SOP/progress gates, both Swift test suites, independent arm64 job
  `99381420096`, x86_64 job `99381420120`, and universal job `99382271354`. The exact
  universal artifact `9745587222` has GitHub digest
  `400ed3436ac98cd8681d268e7e76f88522d2a5dfffc8e49a922db7eb716c3d82` and ZIP SHA-256
  `c2d434ba76895903b1b46d1af06ab3deb84bdd10c0f4ec4bb633aea838b4bb45`.
  The native app, bundled Runtime and bundled analyzer all contained arm64 and x86_64
  slices. Their SHA-256 values were respectively
  `750423b6b2cfa4051483f870524283b9b0db39f95f77634dcb6388de87d0e575`,
  `84dba160da535df2c94ea945f68fb8ceb3d21af91a21c7082afc7fe7bcfa6242` and
  `9b410061f53f0a990578de0de1bdae3e32a370147aae5fe202aed0e7833bc47c`;
  the repository universal verifier and nested ad-hoc signature check passed.
- `scripts/qa-packaged-postproduction.py` v2 then launched that exact packaged Runtime
  on an isolated SQLite database and real loopback HTTP. It materialized two shots and
  all five audio layers, sealed the exact master, deliberately changed the managed
  character reference and received HTTP 409 before analysis, restored it, and executed
  the packaged Apple Vision analyzer. The run recorded ten machine checks and exactly
  one event, replayed byte-identically, bound the resulting manifest to the same seal,
  performed no provider upload, and stopped the Runtime with port 8765 closed. The
  synthetic colour fixture correctly produced perceptual `FAIL` and same-seal visual-QA
  `FAIL` instead of fabricating actor/prop recognition; harness acceptance was `PASS`
  because this is the required conservative result. The canonical report digest is
  `52610d59feac33dfaaff49a6bc12129e3fcc352fe7063bb4eda9b6bd99e9c9f8` and the written
  JSON file SHA-256 is
  `97e8677f2a7c3bd36f36b0e20a1c08e19142d9310a7a99cfaa52841a9b274609`.
- Commit `9b3e5c5` adds the remaining device-level safety mechanics: NumPy-vectorized,
  bounded 8,192-sample mixing; cross-process workspace locking; cooperative cancellation;
  abandoned-stage cleanup; and restart-safe resume that preserves already-materialized
  provider media. It adds regression coverage for byte-identical vectorized mixing and
  cancellation/resume without duplicate result or event. GitHub CI run `33363635917`
  passed all 94 Runtime tests, real HTTP smoke, SOP/progress/OpenAPI/Qingshan checks,
  independent arm64 and x86_64 builds/smokes, and universal merge job `99400722978`.
- The exact universal artifact `9747627654` (GitHub digest
  `b54d201bf579f436502228fdaa5613978d5d344ba0ec85df054bec4bb194a005`) had ZIP
  SHA-256 `76bcfd7784c564ea2a20648b06126e46df13a20e7f0bb89acae9bb17e4175b11`.
  Its main executable, Runtime and visual analyzer had arm64/x86_64 slices and SHA-256
  values `9ac1b48725c2b574c1cca9b09b7e82736edbd96d868d743ed36f0ca063b78003`,
  `f31440302f7a6816ee5f330e6260ca48d252e89ce96019d7ed91cd4ed301ef1f` and
  `9b410061f53f0a990578de0de1bdae3e32a370147aae5fe202aed0e7833bc47c`.
  The universal verifier and nested ad-hoc signature check passed; this is explicitly not
  Developer ID or notarization evidence.
- The exact downloaded bundle then completed a 1,800-second authored, six-shot/five-stem
  materialization device soak on isolated SQLite and loopback HTTP. It completed in
  126.492 seconds (14.2301× real time), sampled the full PyInstaller process tree 125
  times, observed a visible working stage, used 125,632,512 bytes baseline and
  132,399,104 bytes maximum RSS (6,766,592-byte growth), allocated at most
  2,158,096,384 bytes and retained at least 4,605,083,648 bytes free disk. The false
  digest negative case failed closed with HTTP 409 and no accepted result. After Runtime
  restart, all sealed artifacts rehashed identically and the run retained exactly one
  materialization event. Runtime shutdown and port closure were observed. The local
  report is `nalu.packaged-postproduction-qa/v2`, canonical digest
  `312fbd17bdf50fd81375038bdf57b11aa74629121c846f0aa12134d3234d1fa7`, written JSON
  SHA-256 `db84a8d2c98175c4c5cff156ffd2dd9f88c32e992d0ac162c64035ce42b4b539`.
  No provider upload, paid model, non-loopback network or publication call occurred.
- This closes the real local perceptual-executor checkpoint, not SOP-09. Still required
  before `PASS`: on-device recognition and calibrated acceptance against an actual final
  master and real consented references; native-window/accessibility repetition after the
  Mac is unlocked; and
  original-resolution human audiovisual review on the same release candidate.

## SOP-10 · Controlled release and learning loop — IN_PROGRESS

Acceptance:

- Export master, cover, captions, title, description and release package.
- Publishing requires separate, platform-specific approval.
- Child projects require guardian publishing approval.
- Published identifiers and states are verified and stored.
- Platform metrics feed a versioned next-episode director strategy.

QA:

- Dry-run platform adapters and duplicate/replacement protection tests.
- Authorized test-channel publication and state reconciliation evidence.

Current evidence:

- Completed runs with an intact output seal and matching PASS structure and decoded-media
  reports can
  create an immutable offline release package containing title, description, cover,
  captions, master and all sealed hashes. Exactly one cover/master/captions file is
  required; changed metadata cannot replace an existing package.
- Offline packages always set `publishing_enabled` to false and contain no platform
  approvals. Creation does not transition the episode, upload media, call a platform or
  claim publication. Automated fixtures cover too-early creation, exact replay and
  changed-metadata rejection.
- Versioned YouTube and Bilibili dry-run adapters now require a separate matching-platform
  approval and guardian approval for child projects. They compile only immutable sealed
  MP4, WebVTT and cover mappings, bind the exact release manifest and channel reference
  to a duplicate-guard digest, and always record no network call and no episode-state
  change. Exact replay is idempotent; changed approval/channel data and plan tampering
  fail closed.
- Commit `654d7f5`, GitHub CI run `33300480697`: all 67 Runtime tests, OpenAPI
  compatibility, real HTTP smoke, Swift tests, full application build, bundled-Runtime
  smoke, ZIP and artifact upload passed for offline packaging and platform dry runs.
- Still required before `PASS`: explicit user-authorized real platform accounts and test-
  channel publication, durable remote publication identity/state reconciliation,
  replacement publication protection against real remote IDs and versioned metrics
  feedback. Dry-run evidence is not a publication claim.

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
- A read-only local diagnostic now reports total/free space, SQLite size and explicit
  five-GiB minimum/twenty-GiB recommended reserves. The native header refreshes it once
  per minute and always distinguishes sufficient, low and critical space in plain
  language. It never uploads paths or deletes user media; critical space only blocks the
  readiness claim and tells the user to clean the Mac first.
- Commit `273cbc3`, GitHub CI run `33300577745`: all 68 Runtime tests, deterministic
  healthy/warning/critical fixtures, OpenAPI compatibility, real HTTP smoke, Swift
  formatting/presentation tests, full app build, bundled-Runtime smoke, ZIP and artifact
  upload passed.
- Commits `b0d48e9` and `3772426`, GitHub CI run `33326138549`: source builds now
  select an available Python 3.11+ interpreter, validate the real Swift package toolchain
  before the expensive bundle step, inject release/build versions, verify nested code and
  bundled resources, write a ZIP SHA-256 and upload both files. A separate manually
  dispatched workflow imports Developer ID and App Store Connect API-key material only
  from repository secrets, signs nested executables from the inside out with hardened
  runtime, submits to Apple, staples the result, validates Gatekeeper and writes
  commit-bound provenance. The same commit passed Swift tests, complete app construction,
  signature-structure validation, bundled-Runtime launch and artifact upload; GitHub
  reports the `Nalu-Voice-Studio-macOS` artifact archive as 23,732,205 bytes. This CI
  run is intentionally ad-hoc signed and is not notarization evidence.
- Commits `9980676` and `fb4f38b`, GitHub CI run `33327386453`: CI now builds the
  identical commit on Apple Silicon and the official `macos-15-intel` runner, tests and
  launches each self-contained architecture, then refuses to merge if the Info.plist or
  bundled Qingshan resources differ. The canonical artifact requires both `arm64` and
  `x86_64` slices in the native client and PyInstaller Runtime, verifies nested signatures,
  and launches the merged Runtime on Apple Silicon. Runtime, all 77 tests, OpenAPI and SOP
  audits, both Swift suites, both architecture builds, both bundle smokes and the universal
  merge/smoke passed. The downloaded universal ZIP SHA-256 is
  `3942723c916c4c630c6fb775c4882033aec5a6b799f130384fd724dd82c76de7`; GitHub reports
  its workflow artifact archive as 43,395,214 bytes. The manual release workflow now
  performs the same dual build and merge before Developer ID signing and notarization.
- Commit `ac100b5`, GitHub CI run `33327724626` and manually dispatched release rehearsal
  `33327906350`: current official Action runtimes passed without the former Node 20
  deprecation warning. The release workflow validated the product, independently built
  and smoke-tested `arm64` and `x86_64` version `0.1.0-rc1 (1001)`, merged and enforced
  universal slices, launched the merged Runtime, emitted the ZIP/checksum and recorded
  provenance bound to exact commit `ac100b512c25e9c180b6607f3f6ae95bbf8d9980` and both
  architectures. The downloaded ZIP and provenance both report SHA-256
  `e541a44970d54496562dff950dfb2d201967ab6bc404eecbaf4b068f79b16182`.
  Signing/notarization was explicitly false, so this is release-workflow evidence but not
  Developer ID or Apple notarization evidence.
- Commits `a99dcfc` and `d285aa9`, GitHub CI runs `33348618762` and `33349286197`:
  the native supervisor now allows a finite 180-second cold universal-Runtime startup
  window and synchronously terminates its owned Runtime when macOS quits the application.
  Both CI runs passed Runtime tests, arm64 and x86_64 Swift tests/build/smoke, universal
  merge verification and artifact upload. Native QA first reproduced the old 30-second
  false-negative and then found that the first timeout repair orphaned the PyInstaller
  parent/child after Cmd-Q. The final universal artifact `9743140010`, ZIP SHA-256
  `55f933f188234aff8c051c1a10104c307225134440e203d52f652025ddd1a08f`, reached
  the visible “本地制片厂在线 → 可以创作” state in about 35 seconds. Its Runtime was
  the application's child, returned schema v14 health and exposed the postproduction
  lineage route. After Cmd-Q the app, Runtime parent, Runtime child, port 8765 and health
  endpoint were all absent within the observation window. This is ad-hoc-signed native
  lifecycle evidence, not clean-install, Developer ID or notarization acceptance.
- Still required before `PASS`: Developer ID signing, hardened runtime, notarized
  universal release evidence, update channel and clean-Mac upgrade/rollback QA with
  populated multi-episode data. The green universal build is still ad-hoc signed.

## SOP-12 · End-to-end release-candidate acceptance — TODO

Acceptance scenarios:

1. Older adult creates a personal autobiography using voice and personal photos.
2. Guardian and child create a fictional multi-episode story.
3. A 10-episode project preserves identity, voice and narrative state across episodes.
4. One episode fails generation, survives restart, resumes safely and passes QA.
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
- Commit `3772426`, GitHub CI run `33326138549`: authorized, redacted feedback can now
  produce one immutable local review bundle containing expected/actual behavior,
  reproduction steps and only allowlisted Runtime/schema/screen diagnostics. It contains
  no attachments, records `network_call_performed: false`, treats malicious command text
  only as inert data, rejects local-only feedback, requires explicit confirmation, is
  idempotent for an exact request and fails closed on changed or tampered content. Schema
  migration v14, privacy/project export v9, v1-v8 restore compatibility, project deletion,
  OpenAPI and real HTTP smoke passed with all 69 Runtime tests and complete macOS CI.
  Preparing this bundle deliberately does not claim external export or remediation.
- Commit `f044d0b`, GitHub CI run `33326390348`: after the user explicitly enables
  redacted local review, the native client prepares expected behavior, observed behavior
  and reproduction steps from the conversation so an older adult or child does not fill
  a professional form. It reports that media was not attached, no network export occurred
  and no code changed automatically; full Swift, Runtime, application and bundle CI passed.
- Commits `d0edf7c` and `1654b76`, GitHub CI run `33326751267`: the completion SOP is
  machine-audited in CI for all 14 unique sections, valid states, evidence-bearing PASS,
  regression evidence and remaining-work contradictions. The audit currently reports
  `project_complete: false`; this prevents a green module or milestone from being
  promoted to whole-product completion.
- `docs/CONTROLLED_EVOLUTION.md` defines the trust boundary and release state machine.
- Still required before `PASS`: administrator-authorized external issue export, agent
  triage integration, signed staged updater and end-to-end improvement/rollback QA.
