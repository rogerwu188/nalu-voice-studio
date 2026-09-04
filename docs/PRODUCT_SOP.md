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
- Commit `6cbab9745827ba8f4ab62a19f853da22104b4edd`, GitHub CI run
  `33865278670`, Runtime QA artifact `9933855286` and Universal artifact
  `9933867436` (artifact digest
  `sha256:5649b4da1a421e96853880e983ec7892cbfcc0c60a1509e817747124cabd6f14`):
  generic episode transitions now handle an episode deleted after stale preflight as an
  explicit not-found inside the SQLite write transaction instead of dereferencing a
  missing row. A separately simulated concurrent state change remains a conflict and
  cannot be overwritten; neither rejected path appends a lifecycle event. CI passed
  254 Runtime tests, both native Swift suites and architecture builds, Universal merge,
  bundled smoke, packaged project-isolation, staged-update and rollback QA. This
  revalidates the lifecycle concurrency boundary without changing the SOP-01 PASS claim.

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
- Commit `a270ab2`, GitHub CI run `33812804669`, Universal artifact `9915641200`:
  a fresh downloaded-artifact native pass observed the bounded cold start change from
  the visible orange startup state to the green online state in about 45 seconds. The
  large create action immediately added a persisted “未命名故事” row and advanced to
  the first one-question interview prompt; the direct family-material control opened
  and safely cancelled the native `Open` panel; and the Realtime consent sheet kept
  “同意并开始自然语音” disabled without a Keychain credential. The exact QA-created
  project had no assets or runs and was deletion-previewed, removed and verified absent.
  Normal application quit removed the app, PyInstaller parent/child Runtime processes,
  port 8765 listener and health endpoint. `docs/ACCESSIBILITY_QA.md` records hashes,
  process evidence and the limits of this pass. This is native smoke evidence, not the
  outstanding human VoiceOver, real microphone or paid Realtime acceptance.
- Commit `d1e6fd605633d7dcf7f78a04e7a5573a6df5e41f`, GitHub CI run
  `33815093943`, Universal artifact `9916452123`: a production-disabled native QA
  boundary now creates an 18-turn conversation and changes the current transcript only
  when the exact `conversation-scroll` scenario, local-QA flag and existing system-
  temporary Application Support directory are all present. Unit tests reject the
  scenario by default, unknown scenarios, a missing isolation flag and non-temporary
  storage. On the freshly downloaded Universal artifact, the native accessibility tree
  exposed `nalu.conversation.scroll`, displayed the final live transcript at the current
  turn and reported scrollbar position `0.9749780509218613`; a window screenshot also
  showed the latest transcript and listening action together without manual scrolling.
  The Runtime opened only the isolated project database, normal Quit removed the exact
  app and Runtime processes and closed port 8765. `docs/ACCESSIBILITY_QA.md` records the
  artifact hashes, isolation, process and native-window evidence. No microphone,
  credential, provider, paid generation or user project database was used. This closes
  the deterministic native scroll-regression checkpoint, not real-speech, VoiceOver or
  clean-account human acceptance.
- Commit `b88d06e66198e19c24d0c00beb7261f0b68323fe`, GitHub CI run
  `33826230388`, Universal artifact `9920162212` (artifact digest
  `sha256:0fa9b0d4cf6d3f2a59648667ad3ea711b8463695386451330d5f55efa69ad4c7`):
  the native broker was checked against the current official OpenAI Realtime WebRTC,
  client-secret, conversation, tool and VAD contracts on 2026-09-03. It now uses the
  documented `/v1/realtime/client_secrets` and `/v1/realtime/calls` endpoints and
  `oai-events` data-channel label, and fails closed unless the broker response contains
  a bounded, unmodified secret with at least five seconds of usable lifetime and an
  exact `realtime` / `gpt-realtime-2.1` session. Unit tests reject expired, wrong-type,
  wrong-model, whitespace-mutated, oversized and malformed responses. The CI run passed
  193 Runtime tests plus Swift tests, complete arm64 and x86_64 builds, Universal merge,
  bundle smoke, staged-update and rollback QA. No credential was used and no paid or
  live-audio session was started. This closes only the current-contract and broker-
  validation checkpoint; it is not live Realtime acceptance.
- Product commits `f6d9e94`, `72bdbf1` and `e6bc0b2`, GitHub CI run
  `33827397944`, Universal artifact `9920628770` (artifact digest
  `sha256:341a564a03f021b950b852c66a946279ee644a28394077680ff9fa6b82109eef`):
  the WebRTC-to-native bridge now uses one exact `kind` / `value` transcript contract.
  This corrects the prior native lookup of a nonexistent `text` field, which could leave
  successful Realtime user and assistant transcripts out of the visible conversation.
  Both the embedded data channel and native bridge now reject malformed, unexpected and
  oversized events; status values, transcripts, provider errors and tool-call envelopes
  have separate exact allowlists and limits. The first verification run `33826932154`
  exposed a whitespace-coupled embedded-page assertion; the second run `33827132652`
  exposed an unrelated arm64 race between shared URLProtocol fixtures. Neither was
  accepted. The assertion was made semantic and the shared-fixture suite serialized.
  The final run passed 193 Runtime tests, both architecture Swift suites and builds,
  Universal merge, bundle smoke, staged update and rollback. No credential, microphone,
  provider or paid call was used, so live transcript/audio alignment remains unaccepted.
- Commit `7836e03abd857e52c567b17785c58cbea03415a7`, GitHub CI run
  `33828174957`, Universal artifact `9920802527` (artifact digest
  `sha256:5fe936caef537e29e50a8e8d32b842063ba8898767a820d92e79726c50785913`):
  peer failure, prolonged disconnect, provider error and data-channel close/error now
  converge on one idempotent failure path. It tears down capture, permits an explicit
  retry and suppresses duplicate notices; intentional stop remains quiet, and channel-
  identity checks prevent delayed events from a prior connection from failing a new one.
  Embedded JavaScript passed an independent syntax check. CI passed 193 Runtime tests,
  both architecture Swift suites and builds, Universal merge, bundle smoke, staged
  update and rollback. This proves deterministic packaged lifecycle behavior without a
  credential; authorized live network-loss/session-expiry recovery remains outstanding.
- Commit `f12f0023aae2fff94acb9724b6fe24e8c700819d`, GitHub CI run
  `33834341437`, Universal artifact `9922869026` (artifact digest
  `sha256:7f4405a37b41d89ae323b786c6eb789b1b75f7ab520a91ec442e6ece9346b6d9`):
  Realtime interview instructions no longer interpolate editable project data directly
  into the governing prompt. Project names and current questions are whitespace-
  normalized, length-bounded and JSON-escaped inside a block explicitly declared
  untrusted; instruction-shaped titles cannot redefine the answer-first, tool or safety
  rules. Regression coverage includes quotes, newlines, a fake system/deletion command
  and overlong text. CI passed 193 Runtime tests, both architecture Swift suites and
  builds, Universal merge, bundle smoke, staged update and rollback. This closes the
  untrusted-context checkpoint without claiming live model-behavior or paid-audio QA.
- Commit `d6a5ebe9c4d0d6d272bd162b0d7d410f7d722e6c`, GitHub CI run
  `33835006637`, Universal artifact `9923092849` (artifact digest
  `sha256:cb6abd5cc31e69c2b39f3e1d53115394ff6b06481cb1834930408d42478d6712`):
  raw provider, broker, JavaScript and WebKit error descriptions can no longer enter the
  visible Realtime status. Known local failures retain fixed help text; every unknown or
  upstream failure collapses to a bounded Chinese message. A regression fixture embeds a
  fake Bearer credential in an NSError and proves neither the credential nor header label
  is surfaced; static assertions reject the prior raw JavaScript provider-message paths,
  and the extracted embedded script passed an independent syntax check. CI passed all
  Runtime and Swift tests, both architecture builds, Universal merge, bundle smoke,
  staged update and rollback. This closes deterministic error-redaction only; packet
  inspection with an authorized live session remains outstanding.
- Commit `c19e9e3ad0581fa678a778ab22df8b235155c68b`, GitHub CI run
  `33835604189`, Universal artifact `9923264388` (artifact digest
  `sha256:98d13e2f55a77807e527625948b1831339d65e938e13f1a8cb608b2583b0d980`):
  the native bridge now accepts the embedded page's legitimate initial `connecting`
  status instead of classifying it as an unverifiable event and immediately tearing down
  the session. Every client-secret request is also bound to a native generation; stop,
  failure or a newer retry invalidates all older generations, preventing a delayed secret
  response or error from reviving or overwriting a stopped/replaced session. Unit tests
  cover the connecting event plus stopped and superseded attempts. CI passed 193 Runtime
  tests, both Swift suites and architecture builds, Universal merge, bundle smoke, staged
  update and rollback. This closes deterministic initial-state and stale-response races;
  real credentialed connection and interruption behavior remain unaccepted.
- Commit `8ff5fda42dfb5ff8a6492e5f918b74f149704e10`, GitHub CI run
  `33836160599`, Universal artifact `9923496237` (artifact digest
  `sha256:b50dcd81b9f8b92726533a9f61eb569d1d07ba82b5c287b779283275e86d36d6`):
  WebKit capture permission is now bound to all of the consented connecting state, exact
  `https://api.openai.com` origin on port 0/443, main frame and microphone-only request.
  Subframes, other protocols/hosts/ports, camera requests and inactive states fail closed.
  The policy matrix has deterministic positive and negative tests. CI passed 193 Runtime
  tests, both Swift suites and architecture builds, Universal merge, bundle smoke, staged
  update and rollback. This closes code-level origin/capture authorization; the real clean-
  account macOS permission journey and human confirmation remain outstanding.
- Commit `b912d5591c3f2c47b542d292b4d2b7822204d63c`, GitHub CI run
  `33837130557`, Universal artifact `9923764801` (artifact digest
  `sha256:931cb704481c50daff4b624b8a48bbc34f5618bdd45c6b3d7c1ee085cf53367f`):
  local follow-up questions are whitespace-normalized, limited to 1,000 characters and
  sent as an `untrusted_question` JSON field in a separate conversation input item. The
  subsequent response request contains only fixed policy and never concatenates question
  text into model instructions; WebRTC independently rejects empty, non-string and
  oversized values. Injection-shaped text and the embedded JavaScript syntax have
  deterministic regression coverage. CI passed all Runtime and Swift tests, arm64 and
  Intel builds, Universal merge, bundle smoke, staged update and rollback. This closes
  the spoken-prompt data boundary without claiming authorized live model-behavior QA.
- Commit `1c0574800015b5537ae2ffe2694d6d6daf436b3a`, GitHub CI run
  `33837925482`, Universal artifact `9924017024` (artifact digest
  `sha256:9203114bbb6bde2d4714b980115c03cad32f4cd0c3f239521dd0e4fa73780a86`):
  overlapping local spoken-question requests now share one owned cancellation timer and
  monotonically increasing generation. A newer visible interview question supersedes a
  delayed predecessor, while stop and failure invalidate and clear pending delivery.
  Regression assertions bind the generation check, timer ownership and stop invalidation;
  the embedded script passed an independent syntax parse. CI passed all Runtime and Swift
  tests, arm64 and Intel builds, Universal merge, bundle smoke, staged update and rollback.
  This closes deterministic stale-question scheduling without claiming live interruption
  timing or audible human acceptance.
- Commits `da7ffb6c1ed7d32b8c33d05eb5cd89f024466db5` and
  `79b2a4994d6d663f26b3fca42f907008727851ee`, GitHub CI run `33838836778`,
  Universal artifact `9924354675` (artifact digest
  `sha256:da29ebc4658fcfadab01e3c8aed65dd0a67f1456dca20419b4443f4565a64a09`):
  Realtime response events now reject malformed transcript fields and non-array output
  before accessing them, accept at most one exactly named interview tool call per
  response, and bound tool-call identifiers and arguments. Native admission validates
  every call before retaining it, deduplicates replayed call identifiers and fails closed
  after 64 accepted calls per session; restart resets the bounded ledger. Regression
  tests cover malformed output, transcript and function-call shapes, duplicates, the
  session limit, reset and the compiled embedded-page contract. CI passed 193 Runtime
  tests, both native Swift suites and architecture builds, Universal merge, bundle smoke,
  staged update and rollback. This closes deterministic inbound-event validation and
  memory bounding without claiming an authorized paid function-call session.
- Commit `56a303e2dd4ff8675a64baa65dc4e7593dbf5f0b`, GitHub CI run
  `33839596332`, Universal artifact `9924545480` (artifact digest
  `sha256:c1d172a2cea0975b8d9ed283ede62131e4ef000fd9260b9c9cc2b2c7d028ad35`):
  native interview-tool results are now normalized to one line, capped at 1,000
  characters per message/question field and limited to 8,192 encoded UTF-8 bytes.
  Empty or pathological output becomes a fixed rejected result requiring visible
  confirmation. The embedded page independently validates the call ID and serialized
  output before sending them as function-output data; the subsequent response request
  contains no dynamic instructions. Regression tests cover instruction-shaped content,
  whitespace, character limits, encoded-byte overflow and the compiled page contract.
  CI passed 193 Runtime tests, both native Swift suites and architecture builds,
  Universal merge, bundle smoke, staged update and rollback. This closes deterministic
  outbound tool-result bounding without claiming an authorized paid tool exchange.
- Commits `227c00b4c9b8109035597af7ddbd380975bfe4da` and
  `2cd54c02af0a89e16934bcea7b2f9a2014896c32`, GitHub CI run `33840428018`,
  Universal artifact `9924849197` (artifact digest
  `sha256:7c05440150acee53cd2f55ebcf78a32ad4da81705042724612cd26731f05298e`):
  local spoken questions no longer assume cancellation completed after a fixed 100 ms.
  The embedded response gate retains only the latest question, marks an outgoing response
  request before sending it, waits for `response.created` / `response.done`, issues at
  most one cancellation request, and serializes native tool-result responses through the
  same lifecycle. Stop clears all pending work. Static lifecycle assertions and an
  independent embedded-JavaScript syntax parse cover the contract; CI passed 193 Runtime
  tests, both native Swift suites and architecture builds, Universal merge, bundle smoke,
  staged update and rollback. This closes deterministic response serialization without
  claiming live interruption latency or provider ordering acceptance.
- Product commits `8aad256f0042595ef45e46eb8738d55eebc71aa2` and
  `123174b5103d803247a85e104ee1713562998034`, GitHub CI run `33852111301`,
  Universal artifact `9928901204` (artifact digest
  `sha256:47144a4d7cda97df38c77544fda785ebdebde950b3ae02607a46626a6a96b403`):
  the native broker and embedded WebRTC client were rechecked against the current
  official OpenAI Realtime WebRTC, client-secret and conversation-event contracts on
  2026-09-04. Client-secret requests now explicitly ask for a 60-second, `created_at`-
  anchored lifetime and reject an effective secret lifetime above 120 seconds rather
  than silently inheriting a service default. `response.done` now requires an exact
  response object and status; only `completed` may release transcripts or tool calls,
  `cancelled` is cleared without executing a tool, and failed, incomplete or malformed
  terminal responses fail closed. The first CI run `33851815266` was not accepted because
  an older source-contract assertion still expected the previous output lookup; the
  corrected run passed 228 Runtime tests, 75 XCTest tests plus 29 Swift Testing tests,
  both architecture builds, Universal merge, bundle smoke, staged-update and rollback
  QA. No API key, microphone, provider request or paid session was used. This closes the
  current deterministic protocol-drift checkpoint, not live Realtime acceptance.
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
- Current Universal candidate commit `2cd54c02af0a89e16934bcea7b2f9a2014896c32`,
  GitHub CI run `33840428018`, artifact `9924849197` (artifact digest
  `sha256:7c05440150acee53cd2f55ebcf78a32ad4da81705042724612cd26731f05298e`):
  the packaged Runtime created ten ordered episodes in isolated local SQLite, approved
  each script, stopped and restarted the real packaged process, then restored the
  versioned project export into a clean database. The downloaded Universal evidence
  reports database schema `26` before/after restart, identical episode IDs/numbers/states,
  backup digest `bdcc059b4098b5b9028c203ed014340bc989b414fa353fd7a562a88918558bf8`
  and verified report digest
  `8707bbc7592ba607844efedefbc1cda377df999164f7ccb6b44e2bdccdb3b8c7`.
  The downloaded zip also matches its packaged checksum
  `00d6d4cffa578498d4fdef3b30e69175bf60bc6ac0e28926dabc9d6f1e147012`.
  This revalidates deterministic restart/export/import on the current unsigned candidate;
  it does not replace clean-account native-window or accessibility acceptance.
- Commit `c79246bdd31ead6e7068590bee6b967a51fe6fb3`, GitHub CI run
  `33853153296`, Runtime QA artifact `9929181849` and Universal artifact
  `9929332807` (artifact digest
  `sha256:20d4178e9c536b3c10ac480ab327783a4922a227ee42a8f842d8fe85fcc884ac`):
  a dedicated loopback-only planning-isolation rehearsal now starts three project plans
  concurrently, creates ten ordered episodes in each, proves every project/season/episode
  identifier set is disjoint, and verifies that editing one project leaves the other two
  byte-semantically unchanged. It then approves and locks one episode, rejects a later
  overwrite, exports all three projects, restores them into a clean SQLite database and
  confirms identical planning state. A structurally cross-linked season remains rejected
  even after its outer export digest is recomputed. The same rehearsal passed once against
  source and again against the Runtime embedded in the merged Universal app. The downloaded
  report is bound to the exact source commit, schema `26`, snapshot digest
  `c9c5f9c6dcb77e4fcdee02201ea3d8a0b29785fa29b369b084e5d0dff89bee3f`
  and report digest
  `4864982bbeb7173ce44725762237518b6a1a6418a8ae08cbf8c58d9b8e74bfb9`;
  its file digest is
  `20941e6a10d0aa03dec05fe569f6157199b76e3d00f726baf267e3cb28412737`,
  and the packaged zip matches its declared checksum
  `1e6df83093c7d10760a2bd9252f99b3c532c7911ff9d3627e3ed61df554ad547`.
  CI passed 234 Runtime tests, both native suites and architecture builds, Universal merge,
  bundle smoke, staged update and rollback. No user database, provider, paid call or external
  write was used. This closes deterministic current-candidate planning isolation, not the
  outstanding clean-account human voice/accessibility acceptance.
- Commit `222667607d849750033a2baa78a96a270bc7524b`, GitHub CI run
  `33862585733`, Runtime QA artifact `9932766688` and Universal artifact
  `9932880048` (artifact digest
  `sha256:207dec0a803a762c43ef9624da683038c5b108012eb04dc3d19955db4f9c9446`):
  season-plan approval now identifies the exact plan revision displayed to the user.
  The Runtime acquires the SQLite write transaction, re-reads the authoritative latest
  revision and rejects omitted or stale approval requests with conflict before creating
  an approval record. The native visual and voice paths send their displayed revision,
  and the response contract always exposes the bound revision. Regression tests prove
  that an older client cannot approve without a revision and that a plan changed after
  review cannot receive a stale approval. CI passed 247 Runtime tests, 76 XCTest tests
  plus 29 Swift Testing tests on both architectures, the arm64 and x86_64 builds,
  Universal merge, bundled smoke, staged-update and rollback QA. This closes the
  deterministic stale-approval authority checkpoint, not the remaining clean-account
  human voice/accessibility acceptance.
- Commit `452d5103b3d0016503a1d3bb38169e6f330ce0fa`, GitHub CI run
  `33863616633`, Runtime QA artifact `9933144895` and Universal artifact
  `9933266845` (artifact digest
  `sha256:742e86c84b6dc1cd665673c0e9a6da74abcbc118cd0b6b97328b82b85d2cb8cc`):
  season and episode creation now re-read their authoritative parent inside the same
  SQLite write transaction as the child row and season-plan snapshot. A parent deleted
  after stale preflight returns not-found and leaves no child or plan revision, while
  only a real unique-number constraint is reported as a numbering conflict. Direct
  regressions prove both stale-parent paths and unchanged row/revision counts after
  duplicate attempts. CI passed 250 Runtime tests, both native Swift suites and
  architecture builds, Universal merge, bundled smoke, packaged project-isolation,
  staged-update and rollback QA. This closes the deterministic hierarchy-creation
  transaction checkpoint, not the remaining clean-account human acceptance.
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
- Commit `ab3e8598063920cec603e0e530b8d4524480e793`, GitHub CI run
  `33807969208`: every new script revision now carries a versioned Runtime-sealed
  authoring record bound to the exact content and source transcript. The native app
  distinguishes typed and dictated revisions; externally declared AI drafts require
  an exact model, task and digest-only Writer receipt metadata, remain explicitly
  unverified and cannot replace script approval. Reads and project restore reject
  inner-provenance tampering even when the outer export digest is recomputed, while
  legacy rows remain readable as `legacy_unverified`. All 172 Runtime tests, real HTTP
  and offline E2E QA, OpenAPI compatibility, Swift tests, arm64, Intel and Universal
  application builds, bundle smoke, staged update and rollback passed. Universal
  artifact `9913876237` has GitHub digest
  `sha256:6f2ae32c3b9dc03aa139fbba343287be377dbd748d38dff7fc76cbb656ac4cb6`.
  This closes the machine-verifiable authoring-provenance checkpoint, not SOP-04;
  the human acceptance criteria below remain outstanding.
- Commit `9833034a83e4eb57bdbe7e5d70afb792fb909f2c`, GitHub CI run
  `33841511551`, Runtime QA artifact `9925110578` (artifact digest
  `sha256:7329c2e1c7a741ace522188aa138dacde41176979e9f270fc5b6d74e998e63a7`)
  and Universal artifact `9925171593` (artifact digest
  `sha256:b6bdf007e67c25a2e706f9c9119d063d2526e05a0165e5b36f56035c95b96ad2`):
  the child-script approval boundary now has a direct negative fixture proving that an
  unaccompanied approval returns conflict, creates no approval audit row and leaves the
  episode in script review; only a subsequent guardian-authorized confirmation creates
  the single approval record. The 20-test offline structure rehearsal binds this case
  alongside correction/history, stale/revoked approval, production blocking and sealed
  provenance/export restoration, with evidence digest
  `be6186ba12bdea6d29baad4df68b603671bfb77b770dc26ecde667ba6a3925d8`.
  CI passed 194 Runtime tests, both native Swift suites and architecture builds,
  Universal merge, bundle smoke, staged update and rollback. This closes the missing
  deterministic guardian-negative checkpoint, not human spoken-summary acceptance.
- Commit `db1cf4ee557b204fc9d0597052edfb4fd9a6d8f6`, GitHub CI run
  `33854306245` and Universal artifact `9929739932` (artifact digest
  `sha256:fc06b7cf1b6f0240bf44db24ebb8669d4bf3c2f82e565132b4216c3a04ba212d`):
  script revision creation now acquires the SQLite write transaction and re-reads the
  episode's authoritative state before changing it. A delayed request that passed a
  stale preflight can no longer move an episode from preproduction back into script
  review. Creating a legitimate correction after approval preserves the immutable
  approval/history records but clears the current approved-revision pointer, so
  production remains fail-closed until the new revision is explicitly approved.
  Direct regressions cover both stale-preflight and post-approval-correction paths;
  CI passed all 236 Runtime tests, both native Swift suites and architecture builds,
  Universal merge, bundle smoke, project-isolation rehearsal, staged update and
  rollback. The exact authority-race scenarios ran in the source Runtime suite; the
  Universal artifact proves the accepted code was packaged but is not represented as
  a direct packaged transaction rehearsal. This closes the current deterministic
  authority-gate revalidation checkpoint, not the remaining human voice acceptance.
- Commit `b968f68ac3b1076c8e249c51c1a13ff291c7205c`, GitHub CI run
  `33864513654`, Runtime QA artifact `9933573905` and Universal artifact
  `9933581597` (artifact digest
  `sha256:ec003ea93a2249d990c6615e6ec61976e3611962b0f3157607afe013231d6cef`):
  script approval and revocation now resolve the current episode, season and project
  relationship under the same SQLite write lock as the lifecycle event and approval
  record. A project hierarchy deleted after stale preflight returns not-found and cannot
  write an approval, revocation or transition using a stale project identity. Direct
  negative regressions cover both operations. CI passed 252 Runtime tests, both native
  Swift suites and architecture builds, Universal merge, bundled smoke, packaged
  project-isolation, staged-update and rollback QA. This closes the deterministic script
  parent-authority checkpoint, not the remaining human voice acceptance.
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
- Product commits `6fcb56164f8e0ded44e16013f9ec1cb1eb9d46e2` and
  `c37744c0fedf046b3213e2bc47c6e5793bb80f00`, GitHub CI run `33842279700`:
  child character-photo and voice-reference imports now have direct negative QA at
  both Runtime entry points. A complete subject-consent request without guardian
  approval returns 409 before any database row or managed file is created; attempting
  to re-register an already managed URI cannot bypass the same rule. The authorized
  path creates exactly one managed file and one guardian-bound grant receipt. The
  21-test offline E2E rehearsal binds this fixture to the guardian-child scenario and
  explicitly remains non-release evidence. CI passed 196 Runtime tests, lint, OpenAPI,
  real HTTP smoke, offline rehearsal, both architecture Swift suites and builds,
  bundled-Runtime smoke, staged update, populated rollback and Universal merge.
  Runtime QA artifact `9925355440` has digest
  `sha256:a4af0e8cd638a18d816a130ea516d6097157d22eb0447cfb7a88fee976ad6802`;
  Universal artifact `9925403717` has digest
  `sha256:c4ba7983f988707ef8e53e6376c08bfaf6ed00f346951a36010d901cc92c8104`.
  This closes the current automated child-biometric checkpoint, not human privacy,
  deletion, OCR or signed-install acceptance.
- Commit `d6d056eba0d1c1a9359fdb5f6a774ef8963d894e`, GitHub CI run
  `33855212529` and Universal artifact `9930110515` (artifact digest
  `sha256:e5c65d78ce42aaadd72c84b202ec881f0ae3cc114f58361ca14e855fb2b10455`):
  every managed local URI now has a single asset-record owner. The legacy registration
  endpoint checks ownership after acquiring the SQLite write lock, so concurrent
  requests cannot create two records whose later deletion would remove the same file
  and strand the survivor. A five-run local concurrency stress and CI regression prove
  exactly one of two simultaneous registrations succeeds, the rejected request creates
  no row, and the managed bytes remain intact. CI passed 237 Runtime tests, both native
  Swift suites and architecture builds, Universal merge, bundle smoke, project-isolation
  rehearsal, staged update and rollback. The Universal artifact proves the fix is in the
  package; this is a deterministic storage-ownership checkpoint, not human privacy,
  deletion, OCR or signed-install acceptance.
- Commit `c01b60f745a730bf5b145d1c5aff9a53ed66393c`, GitHub CI run
  `33855982828` and Universal artifact `9930437329` (artifact digest
  `sha256:a958c9af8eabe2b5d579a4d0233b7cf44e907a206454be71bbca02b023fc5936`):
  immutable production dependency lookup and asset-record deletion now execute under
  one SQLite write transaction. Even when the service-level preview is stale and says
  an asset is deletable, a production snapshot committed before the transaction causes
  a stable conflict response; the database record, managed bytes and run binding all
  remain intact. CI passed 238 Runtime tests, both native Swift suites and architecture
  builds, Universal merge, bundle smoke, project-isolation rehearsal, staged update and
  rollback. This closes the deterministic dependency/deletion race checkpoint, not
  human privacy, complete deletion, OCR or signed-install acceptance.
- Commit `ba90f6bdc43c1aca310d6027be27b6880d3a8368`, GitHub CI run
  `33857077039` and Universal artifact `9930849213` (artifact digest
  `sha256:3a2455e7b5f1a20e876ae770538a88d4b29d0fb62144a50ff8c677c3d80ac014`):
  destructive project deletion now binds the user's preview to exact asset and
  production-run inventories and revalidates both under the final SQLite write lock.
  If a production snapshot appears after preview, deletion fails closed, all staged
  original asset/run directories are restored, the late snapshot remains registered,
  and `verified_absent` is not emitted. Successful deletion now verifies the complete
  project asset root, every bound run root and all project privacy archives rather than
  only paths that happened to be staged. CI passed 239 Runtime tests, both native Swift
  suites and architecture builds, Universal merge, bundle smoke, project-isolation
  rehearsal, staged update and rollback. This closes the deterministic stale-inventory
  deletion checkpoint, not human privacy/deletion, OCR or signed-install acceptance.
- Commit `0db49b5bf0668cb349999fdb72417c3c3c49ddd8`, GitHub CI run
  `33857969942` and Universal artifact `9931137482` (artifact digest
  `sha256:9fab715a9365bed08ad1d0c85e0cd41ecf8884d4d2c8faa996acf87e578a102f`):
  privacy export reads each managed medium exactly once, verifies that byte snapshot
  against its import-time SHA-256 when available, and writes those same bytes into the
  ZIP. Modified local media now fails closed before an archive is created; after the
  original bytes are restored, the archived payload, manifest byte count and manifest
  digest agree exactly. CI passed 240 Runtime tests, both native Swift suites and
  architecture builds, Universal merge, bundle smoke, project-isolation rehearsal,
  staged update and rollback. This closes the deterministic privacy-export byte-integrity
  checkpoint, not human privacy/deletion, OCR or signed-install acceptance.
- Commit `3a1150e785e88b6f6b67bfb796759c0a365a66fe`, GitHub CI run
  `33858842840` and Universal artifact `9931493742` (artifact digest
  `sha256:71c07398210726e7516d03dfb06ed2152ad8b87187708782b1ed49885834aad4`):
  memory-card confirmation now rechecks the exact reviewed revision after acquiring the
  SQLite write lock, and evaluates narrative conflicts under that same lock. A correction
  arriving after a stale preflight cannot confirm the newer draft, and two concurrently
  confirmed, mutually conflicting event/place cards cannot both become narrative authority.
  CI passed 242 Runtime tests, both native Swift suites and architecture builds, Universal
  merge, bundle smoke, project-isolation rehearsal, staged update and rollback. The source
  Runtime tests directly exercise the transaction races; the Universal artifact proves the
  accepted implementation is packaged, but is not a substitute for clean-account spoken
  review. This closes the deterministic memory narrative-authority checkpoint, not human
  privacy/deletion, OCR or signed-install acceptance.
- Commit `5163ac2853d869ad61b1038d5f7421a54cad518b`, GitHub CI run
  `33859773956` and Universal artifact `9931842217` (artifact digest
  `sha256:128557e3f970298deb06db3d1303db9176b945c96e74d767755eb4cd883eb8ed`):
  memory-card create and update now re-read project ownership, biometric consent and child
  guardian authorization under the same SQLite write lock as the card/revision write. A
  revocation arriving after the service preflight therefore prevents a new card or an
  upgrade to `visual_generation`, leaving no card or extra revision behind. Both race
  fixtures passed ten repeated local runs; CI passed 244 Runtime tests, both native Swift
  suites and architecture builds, Universal merge, bundle smoke, project-isolation
  rehearsal, staged update and rollback. The Universal artifact proves the accepted code
  is packaged; it does not replace human consent-language or accessibility QA. This closes
  the deterministic memory visual-consent checkpoint, not SOP-05 as a whole.
- Commit `5321b2494275bdb4f68c26bfa0aae3e722eab554`, GitHub CI run
  `33860750645` and Universal artifact `9932331421` (artifact digest
  `sha256:8141a7e1f9aa9c6943bb308da54f839cd4ff8a456d4034243ab665375e65717e`):
  asset registration now revalidates project, season and episode existence and ownership
  under the same SQLite write lock as the asset and consent-receipt insert. If any scope is
  deleted after managed bytes are copied but before registration, the request returns a
  stable not-found response, creates no database row and removes the staged file. Dedicated
  project-, season- and episode-scope race fixtures each passed ten repeated local runs; CI
  passed 247 Runtime tests, both native Swift suites and builds, Universal merge, bundle
  smoke, project-isolation rehearsal, staged update and rollback. This closes the current
  deterministic three-level asset-scope checkpoint, not human privacy/deletion or signed-
  install acceptance.
- Product commit `2812eed304733cebbbe8c22af282b1ac24882d87`, GitHub CI run
  `33876769475`: managed photo, recording and document imports now write bytes and a
  digest-bound recovery marker in a private directory, sync both files and the directory,
  then durably promote the directory before the SQLite asset transaction. Runtime-start
  reconciliation removes abandoned staging directories, deletes a promoted import with no
  database owner, and preserves a committed import only after checking its project, URI,
  byte count and SHA-256 against both SQLite metadata and the marker. Automated process-exit
  QA covered the two database boundary windows: before commit, restart left zero rows and
  zero managed files; after commit but before marker cleanup, restart retained exactly one
  registered digest-verified asset and removed the recovery marker. All 270 Runtime tests
  and the Runtime, Apple Silicon, Intel and Universal jobs passed, including child-biometric
  denial, scope races, privacy export, bundled-Runtime smoke, project isolation, staged
  update, populated rollback and controlled-evolution checks. Runtime QA artifact
  `9938255148` has digest
  `sha256:8d527f69decb61bf07b7eef3ee2862323fad12205e9dfb3c3a0f861086b56604`;
  Universal artifact `9938468938` has digest
  `sha256:130095d1bf4aa49efe066aa9c1712610c90e23d78745d63ffb99aadf92f06173`.
  This closes the deterministic managed-import crash boundary, not human privacy/deletion,
  clean-account OCR, voice archive or signed-install acceptance.
- Product commit `d6232d5c16a944b7be72da3a0a11fc560df09be7`, GitHub CI run
  `33877915504`: deletion of a managed family photo, recording or document now first
  atomically retires its complete asset directory into a private hidden deletion stage and
  syncs the parent directory before deleting the SQLite record. If the database transaction
  fails, the original directory is restored; Runtime-start reconciliation restores staged
  bytes when their database owner still exists and removes them when the committed record is
  absent. Automated process-exit QA covered both database boundary windows: after file
  retirement but before database deletion, restart restored exactly one registered asset and
  its original bytes; after database deletion but before byte removal, restart removed the
  private stage and left neither a row nor managed media. All 271 Runtime tests and the
  Runtime, Apple Silicon, Intel and Universal jobs passed, including bundled-Runtime smoke,
  project isolation, staged update, populated rollback and controlled-evolution checks.
  Runtime QA artifact `9938711928` has digest
  `sha256:3dabb4f985cb9d974520c431bec9c6235591b45e8acaae68360fa0de0b94607b`;
  Universal artifact `9938849546` has digest
  `sha256:14e79d9be90dc62e8a5c6eae36ab3c6b51b3bb0dded19d2dbde57ec29c228b1e`.
  This closes the deterministic managed-deletion crash boundary without leaving media outside
  privacy controls; it does not replace human privacy/deletion, clean-account OCR, voice
  archive or signed-install acceptance.
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
- Commit `a567ee5`, GitHub CI run `33489248611`: the latest upstream release
  `v2026.09.01` was checked out by exact tag and commit
  `098361366538b74eff3985af0d28e5462cb29535` in isolation. Its complete tracked tree
  (`c84f4addeded3a4b1346ebd759a9f24150fd195d4eab5faceac1c39a6b82cafa`) and gate
  registry (`a6308af097da8cac3c664466ba665277970391587c44bb1dd949421901e8ac6b`)
  are bound to a machine-readable quarantine record. The upstream integrity function
  found 69 gates and 66 coded/runtime-bound gates but still failed on eight exact missing
  paths plus one host-specific absolute test path. The latter had been masked because
  the unrelated file existed on the audit Mac; Nalu's independent portable audit now
  rejects it on every host. Nalu retained `v2026.08.29.1`, prohibited paid execution and did not claim
  the advertised targeted subset as the complete registered suite. All 114 Nalu Runtime
  tests, real HTTP smoke, both architecture builds and the universal artifact passed;
  artifact `9793232570` has GitHub digest
  `sha256:1d2c1a37b3ba5bb50adbf0ed09ac0ae34a7258c439ee66563d4f76688379c3cf`,
  inner ZIP SHA-256 `ea3c99a101561c807aadd219f0dca1e1bddbc193dec4e6628186fe0d78ab299d`,
  staged-update evidence SHA-256
  `c6cd5b8d4fee0900196d37007a2dcc8934a62a04c825198ea0d42c2ef1c39f30` and rollback
  evidence SHA-256 `c55fc9364a81783328719c2eac995a4d288c2c93c63a3f95c5b439ef424b0239`.
  The original evidence therefore required correction; only a new CI run of the portable
  audit can close the candidate-quarantine checkpoint. This is not SOP-07 or promotion.
- Commit `1349636`, GitHub CI run `33490668498`: the corrected independent auditor
  shallow-cloned the exact tag on clean Linux without importing or executing upstream
  Python, recomputed the 1,723-file tree and registry digests, parsed every declared
  runtime binding and reproduced all nine quarantine failures, including the absolute
  path even though that unrelated file is absent on CI. All 116 Runtime tests, real HTTP
  smoke, Apple Silicon, Intel and universal builds passed. Universal artifact
  `9793822234` has GitHub digest
  `sha256:e32c92bec9f4caef482ee3afcde7fc29619425d2ba9d280d7ce538cb3d2a4e9e`,
  inner ZIP SHA-256 `f1351a760600fffcc213daee690574b5db10d49845bb5903faded2f9cb6b5542`,
  staged-update evidence SHA-256
  `e21c3419f1fc4726d02fe708ede7805d4546381b61150412b32357792cb3f631` and rollback
  evidence SHA-256 `3a57c9aa212219532595588c739356970c237d9ada2ee7a5dc42d7e758326274`.
  The packaged quarantine record exactly matches source SHA-256
  `8daf4d3a609ae467626556ab6106752b24e06cb14604d76487ae15d47d1f083f`.
  Daily discovery and main CI now rerun this isolated comparison; drift fails closed.
  This closes only the corrected candidate-quarantine automation checkpoint.
- Commits `2c9b571` and `9bef1ee`, GitHub CI run `33504514059`: Nalu isolated and
  reproduced the current Qingshan `v2026.09.01.3` candidate at exact commit
  `c58c43b5536370835cc39e0be099a8b62324b7de`, tracked-tree SHA-256
  `aac9a7ce7ce2ae905743093248b904b8a560ed30694f3338847a6c0047463763` and
  unchanged registry SHA-256
  `a6308af097da8cac3c664466ba665277970391587c44bb1dd949421901e8ac6b`.
  Its useful duration-preservation, explicit noncombat and native-delivery-resolution
  corrections were mapped into Nalu's versioned compiler and only paid-I/O boundary,
  while the same eight missing registered paths and one absolute path kept the candidate
  quarantined and the active pin unchanged. Immediately before any future transport call,
  finite model-bounded duration, explicit nonconflicting combat classification, honest
  native/delivery resolution and silent-upscale prohibition are now mandatory. Rehashed
  semantic tampering, non-finite duration and negative-prompt combat words with an
  explicit noncombat declaration have dedicated offline regressions. All 127 Runtime
  tests, portable candidate reproduction, real HTTP smoke, both architecture builds,
  release verification, packaged Runtime smoke, populated rollback and Universal merge
  passed without a credential, provider call or paid task. Universal artifact
  `9799233262` has GitHub digest
  `sha256:1786f9f2e628056a9433e8964a0747bbc5a90693b64f3ec3b9d228b0142c06de`
  and independently downloaded inner ZIP SHA-256
  `774cb67de80fb0449b69f98b4f4cae273b7885416f2cc20cecde65ce6c607145`.
  Its packaged candidate audit is byte-identical to source at SHA-256
  `dffb3a986f6dd43f91c4182fe1d249831700eff59791d66639ec8ba042212b25`,
  reports all nine failures, `QUARANTINED` and `paid_execution_allowed: false`; the
  Universal Runtime contains the `nalu_runtime.qingshan_compilers` archive module and
  has SHA-256 `87a79dcfaf3fc034a44937ae1d25131a0e2c69de4467718e18b5999f6252efbb`.
  This closes only the current-release productization checkpoint, not SOP-07.
- Product commit `76b7283077aedccd8470088f1441c839ba7d6bb7`, GitHub CI run
  `33571104271`: Nalu discovered and independently reproduced Qingshan
  `v2026.09.01.7` at exact commit `9c40a28d07ee9c48aed9307cbc7726a1bd992379`,
  tracked-tree SHA-256
  `6535a3697c17809a4126b67b4269e99d2b2eeb7254a161626ef1ac648e1d2e46`
  and unchanged registry SHA-256
  `a6308af097da8cac3c664466ba665277970391587c44bb1dd949421901e8ac6b`.
  The same eight missing registered paths and one host-specific absolute path remain,
  so the candidate is still `QUARANTINED`, cannot replace the active pin and cannot
  authorize a provider charge. The packaged audit is byte-identical to source at
  SHA-256 `ecd7cd5ee51c0e4d015665bc000f0550746f48f5860a75acafa80940ade71783`.
  Nalu productized two safe deltas: the final paid projection now preserves adapter,
  profile, logical-model and provider-model identity; local postproduction now applies
  bounded static release normalization and independently measures decoded published-mix
  and final-master EBU R128 integrated loudness, loudness range and true peak through
  bundled Libav before completion. Self-reported loudness cannot satisfy the gate.
  All 144 Runtime tests, real HTTP smoke, offline E2E, isolated candidate reproduction,
  arm64, x86_64 and Universal packaging passed. Universal artifact `9825078541` has
  GitHub digest
  `sha256:cf7062e95317f2dc4c59a751e349ec1d93a7ba2fbf3ef5cc952ce54d3605bf26`
  and independently downloaded inner ZIP SHA-256
  `699418ea08eb1041cd45e87d72cd147e81fd7e877fcccc4ce6c4ed5b773a2d7b`.
  This closes only the `v2026.09.01.7` quarantine/productization checkpoint, not SOP-07.
- Product commit `872cb3d7aca9d439dbd7045c9474a68be13b7705`, included in
  progress commit `0a102065797c37df2d94357a9d53a5c71ff224cb`, GitHub CI run
  `33685909456`: Nalu independently reproduced Qingshan `v2026.09.02.2` at exact
  commit `671dfb09f62fbf0f6f9911bad52a40a5a80cd327` and tracked-tree SHA-256
  `eb720810fed36993dc4411a288ee5493ccebcddfedf9b87e187c6bc4177e2d6b`.
  The unchanged registry still fails on the same eight missing paths and one absolute
  host path, so the candidate remains quarantined and cannot authorize a paid task or
  replace the active pin. Nalu productized three safe execution semantics: a scene-first
  request requires a digest-bound entry-state-only keyframe; every same-scene continuation
  requires the previous accepted provider task, receipt and real final-frame digest; and
  local postproduction measures provider-media duration, requires an explicit editorial
  source window and rejects whole-media passthrough. All 150 Runtime tests, portable
  candidate reproduction, HTTP/offline E2E, arm64, Intel and Universal Swift builds,
  bundled-Runtime smoke, staged update and rollback passed. Universal artifact
  `9868297261` has GitHub digest
  `sha256:b76f9adae7221cd8e8cb5c4d465903994ed3491abe59171b5ffe91775eb2a9ad`.
  This closes only the `v2026.09.02.2` quarantine/productization checkpoint, not SOP-07.
- Commit `f35739d30895e98b2f03d2bd848ca5e1d21f89b6`, GitHub CI run
  `33695323164`: the paid boundary now binds all director-authored camera geometry—shot
  scale, height, side, axis, motion, start/end framing, motivation and lens intent—to a
  canonical digest. Automatic enrichment is restricted to the declared optical/style
  allowlist, and locked plans reject every automatic addition. Changed protected fields,
  missing authority, digest drift and unauthorized enrichment fail before provider I/O.
  All 155 Runtime tests, HTTP/offline E2E, Swift tests, arm64, Intel and Universal builds,
  bundle smoke, staged update and rollback passed. Universal artifact `9871717686` has
  GitHub digest
  `sha256:b9394f1a8bf9d8289390eb8dba2dd96b1845fd219a2724bd0d2f14c30e3d291b`.
  This closes the camera-authority contract checkpoint, not SOP-07.
- Commit `20672f9088d0535ad7c92fd46489898427ef2606`, GitHub CI run
  `33695946593`: every visible prop now requires an ordered, complete entry/exit
  state contract for owner, hand, position and disposition. Ownership, hand or
  disposition changes require explicit writer authority, while the opening state
  must be bound to a visually confirmed frame digest before provider I/O. Missing
  props, reordered contracts, incomplete state, unauthorized handoffs and invalid
  visual evidence fail closed. All four Runtime and macOS CI jobs passed; Universal
  artifact `9871934289` has GitHub digest
  `sha256:3aa2685e74978aab0d78086568d37056fdeca822471ca8c874741097905f6610`.
  This closes the visible-prop-state authority checkpoint, not SOP-07.
- Commit `946ca07f2fa2a57ade84b9761de5e6cc0d1871bd`, GitHub CI run
  `33696635302`: an episode's first scene must explicitly classify its relationship
  to the prior episode's active event as continuing, resolved or elapsed. A continuing
  event cannot restart as a static tableau and must carry a writer-authored continuation
  action through the only paid boundary. Missing relations, static reopening and absent
  narrative authority fail before provider I/O. All 162 Runtime tests and all four
  Runtime/macOS CI jobs passed. Universal artifact `9872175147` has GitHub digest
  `sha256:71b31c0e1f18cb5b019cb5d53a343a63b81b23f84844f33ae27e8203bfb3b2fe`.
  This closes the cross-episode active-event checkpoint, not SOP-07.
- Commit `d88db800998133c36a329c4a11e9668e6384f47b`, GitHub CI run
  `33697265338`: every shot submitted to a future paid transport now carries an
  explicit entry/exit state-delta across position, posture, contact, possession,
  integrity or momentum. `CHANGE` requires a real changed endpoint; a deliberately
  static shot must use `INTENTIONAL_HOLD` with a writer-authored dramatic reason.
  Missing dimensions, duplicate/unknown dimensions, implicit no-change and unreasoned
  holds fail before provider I/O. All 166 Runtime tests and all four Runtime/macOS CI
  jobs passed. Universal artifact `9872367379` has GitHub digest
  `sha256:76ea7e24a9b2614afe9a2f5c79f0b147f0245632c5bd0adf42e1010a22d8b4f0`.
  This closes the shot state-delta checkpoint, not SOP-07.
- Commit `0fe4cf18f2edc79b007be1970fecf99092d91590`, GitHub CI run
  `33788826554`: Nalu independently checked out Qingshan `v2026.09.03.3` at exact
  commit `c88f875ceb1c6b5bbee037149af44594cbe9a53d`, recomputed the 1,819-file tree
  SHA-256 `4de2cbe4be467e706f35ad68509af5ac5912cca0438e5aaf2c188599c27ca12e`
  and changed registry SHA-256
  `caa51794451e33c5d0c3c1e7cc08c7e3d54293ce149509c12350dd84caed878e`.
  A new no-execution audit verifies the MIT license binding, zero-dependency core,
  stable `qingshan_engine.cli:main` entry point, version-matched portable-core manifest,
  complete relative required-file closure and absence of private BacklotOS/AgentCut
  imports in the public package. The former absolute-path defect is fixed, but eight
  registered evidence paths are still missing, so the candidate remains quarantined,
  cannot replace the active pin and cannot authorize paid execution. All 168 Runtime
  tests, clean Linux candidate reproduction, HTTP/offline E2E, Swift tests, arm64,
  Intel and Universal builds, bundled-Runtime smoke, staged update and rollback passed.
  Universal artifact `9906713225` has GitHub digest
  `sha256:ac7bfccd624c6405a23977f1ef399eb14e433179370e0846e162d426e65722fa`.
  This closes the public-engine-interface audit checkpoint, not SOP-07.
- Commit `562c602b9ffb06b3f222195b9bac45c5ab0dd6b4`, GitHub CI run
  `33790673885`: the public-interface audit now requires all six stable Qingshan 0.3.0
  commands (`init`, `doctor`, `test`, `writer-doctor`, `video-preflight` and
  `release-preflight`) and binds the repository-owned production gate, standard
  submitter, platform release preflight and stock-FFmpeg renderer as portable-core
  entry points. This deliberately does not replace Nalu's stricter durable submitter,
  package-bound authorization, idempotency, ambiguous-charge quarantine or decoded-media
  release QA. All 168 Runtime tests and all four Runtime/macOS CI jobs passed; Universal
  artifact `9907427075` has GitHub digest
  `sha256:0d66ea1c90551f4ccacff5dbaf64cb9b66a1dffa96e8163498b0fee8aff32b4f`.
  This closes the portable-command-surface checkpoint, not SOP-07.
- Commit `8ece75411457076c5e0602516351560fb811c189`, GitHub CI run
  `33792752813`: Qingshan `v2026.09.03.4` was independently checked out at exact
  commit `856870f1aa97452b85b229a118566b37219f2683`, tracked-tree SHA-256
  `f5da9588330ca35355d9121401e19a2df56834a720af0764b529f7c004126e8b`.
  All eight formerly missing registry paths are present; the independent static audit
  now reports 69 registered gates, 66 coded gates and 66 runtime bindings with registry
  status `PASS`. Promotion still fails closed because the installable package/CLI version
  is `0.3.0` while portable-core manifest SHA-256
  `95867754527f088328e48261aa9dcf1d2ed62b4834efe968630ba93998da3ff3`
  declares `0.3.1`. The evolved audit keeps registry and public-interface status
  independent and also binds Writer v2's provenance/receipt schemas, authorized agent
  identities, rejection of generic model aliases and dispatcher provenance import
  without importing or executing upstream code. All 170 Runtime tests, clean candidate
  reproduction, HTTP/offline E2E, Swift tests, arm64, Intel and Universal builds,
  bundled-Runtime smoke, staged update and rollback passed. Universal artifact
  `9908224100` has GitHub digest
  `sha256:2ffbbe0835e61ba017a54c970c1beb63f1bbd5edbb4009c86e05820b279c1bb7`.
  This closes the registry-closure/Writer-v2 audit checkpoint, not promotion or SOP-07.
- Commit `ab3e8598063920cec603e0e530b8d4524480e793`, GitHub CI run
  `33807969208`: Nalu productized the safe Writer v2 provenance semantics independently
  of the quarantined upstream release. User text, user dictation, externally generated
  and externally assisted scripts are separated; generic model aliases fail validation;
  content, transcript, exact model, rules/input and declared receipt digests are sealed.
  Client-declared external receipts are never reported as verified and the Runtime makes
  no provider call. Export/import and direct SQLite tampering regressions fail closed.
  All four Runtime/macOS jobs passed and Universal artifact `9913876237` has GitHub
  digest `sha256:6f2ae32c3b9dc03aa139fbba343287be377dbd748d38dff7fc76cbb656ac4cb6`.
  This closes Nalu's untrusted writer-declaration checkpoint, not trusted receipt
  reconciliation, Qingshan promotion, paid-provider QA or SOP-07.
- Product commit `c609be13bd8068a9031c277ca7dfad9589b8a57c`, GitHub CI run
  `33810320445`: Nalu now accepts the exact raw bytes of a Qingshan Writer v2
  `qingshan.canonical_writer_run_receipt.v1` artifact through a separate local
  reconciliation boundary. It rejects duplicate JSON keys, altered receipt bytes,
  unsupported schemas or states, unknown Writer agents, generic or mismatched
  provider/model/task identity, input/rules/content digest drift, and invalid or
  reversed timezone-aware task intervals. The Runtime stores only a normalized,
  immutable `nalu.writer-receipt-reconciliation/v1` record, binds it uniquely to the
  exact sealed script provenance, includes it in project export v21 and any later
  production package, preserves v1-v20 import compatibility, and detects direct SQLite
  or rehashed-export tampering. Reconciliation remains deliberately honest:
  `artifact_binding_verified` is true, but `provider_execution_verified` and
  `network_call_performed_by_runtime` are false because the upstream receipt is not
  cryptographically provider-signed. All 183 Runtime tests, lint, OpenAPI compatibility,
  SOP/progress/release audits, current-candidate reproduction, real HTTP smoke and
  offline E2E passed. Native Swift tests, application build, bundled-Runtime smoke,
  staged update and populated rollback passed on Apple Silicon, Intel and the merged
  Universal build. Runtime artifact `9914602968` has GitHub digest
  `sha256:e8916f3e3ec95d701e3cd44668951c810da8f826cea1477aba002901119e8eb9`;
  arm64 artifact `9914599555` has digest
  `sha256:e077dcde3fe82965b672fac890f18d556f146545b949dd69fec6929489b52e70`;
  Intel artifact `9914660808` has digest
  `sha256:dd7d865c4c54ae760ef1f44d739db85f54b46a4dde1a7a948d3a92bc749d29ca`;
  Universal artifact `9914707196` has digest
  `sha256:56b28c4a7423180b197106e38650e369c5f9978a2a6882b68a69413ee95b09bf`.
  This closes the local Writer-receipt artifact-binding checkpoint, not real provider
  execution verification, Qingshan promotion, paid-provider QA or SOP-07.
- Product commit `f8e1faed776564ffa29e449b6902d02e9d4a8012`, GitHub CI run
  `33812094698`: Nalu now exposes a second, disabled-by-default Writer verification
  boundary after local receipt binding. It requires the exact receipt-record digest,
  explicit read-only confirmation and a stable idempotency key; persists intent before
  invoking an injected authenticated read-only verifier; and matches the remote provider,
  exact model, task ID, completed state, receipt digest and task interval. Successful
  results are separately sealed and packaged without claiming that Nalu generated,
  spent credits or performed an external write. Unexpected transport failures, malformed
  evidence and identity mismatches persist as `ambiguous`, block production and cannot be
  retried automatically. SQLite migration v26, project export v22, v1-v21 compatibility,
  restore/direct-database tamper detection and production-package propagation passed.
  Deterministic verifiers cover only this local contract and are explicitly not treated
  as real provider evidence. All 186 Runtime tests, lint, OpenAPI compatibility,
  SOP/progress/release audits, current-candidate reproduction, real HTTP smoke and
  offline E2E passed. Native Swift tests, application build, bundled-Runtime smoke,
  staged update and populated rollback passed on Apple Silicon, Intel and the merged
  Universal build. Runtime artifact `9915224324` has GitHub digest
  `sha256:ed5e3ccff22038b6137949ddf7b702c86d3435bb0b101070733f3bda0d1044fd`;
  arm64 artifact `9915233336` has digest
  `sha256:903b8ab125551b0a34e6de704c677d824ee000346173954cfd8441b37cd3c0a8`;
  Intel artifact `9915336618` has digest
  `sha256:e200941aa96fb7357ad3d8141dd103ccaf0d6a2aa3c144ffb21d4ded0caab95f`;
  Universal artifact `9915368729` has digest
  `sha256:a64d972fa9c669bd7bce3fa296c5420193f50c082900548e2782948a63c5ddd5`.
  This closes the safe provider-reconciliation contract checkpoint, not an actual
  provider lookup, Qingshan promotion, paid-provider QA or SOP-07.
- Product commit `f5192ead0bddab68714b1f2d4db2f601d8334e7f`, GitHub CI run
  `33816952385`: Nalu independently checked out Qingshan `v2026.09.03.7` at exact
  commit `a6264982b0548d3807de16e7d9979d79c4ba48b3`, recomputed tracked-tree SHA-256
  `bd958b67953c03ccbdaf06b0c78a56172cf2c8d4898c771a8d69dc30b633bc13`,
  registry SHA-256 `0b7d478904638f0d9e22452971b7aa8d95b9e7445355b53e364ff187fd0613a4`
  and portable-manifest SHA-256
  `61db4eeaad2f26643713f38e0c9ebaedf6bea952e8a8305661d8ae9b8add676a`.
  The static registry and Writer-v2 audits pass with 69 registered gates, 66 coded
  gates and 66 runtime bindings. A new CI gate then executes the exact immutable
  checkout with credential-like environment variables removed: core doctor passes,
  all 33 registered portable modules run, 208 tests pass with one declared skip, and
  Writer doctor adds six passing tests. Promotion remains fail-closed because the
  installable package/CLI still reports `0.3.0` while the portable manifest reports
  `0.3.1`; the candidate is therefore `QUARANTINED`, does not replace the active
  `v2026.08.29.1` production pin and cannot authorize paid execution. All 188 Nalu
  Runtime tests, lint, contract/audit gates, real HTTP smoke and offline E2E passed;
  Swift tests, arm64, Intel and Universal builds, bundled-Runtime smoke, staged update
  and populated rollback also passed. Runtime artifact `9916926086` has GitHub digest
  `sha256:c423f36f8decaa3a41a56c6e1a6e896d2a2c403d30a8ffc34aa77589b87bc034`;
  arm64 artifact `9916918844` has digest
  `sha256:aefb24a92ae9043370839d77aa80d0c78ba4ab37749e607894cd8c4e53e958c0`;
  Intel artifact `9916976161` has digest
  `sha256:4477be2a6d3e57e4dc9d4e475768c6c7fbe77192f8e479a93c72e3cc35c74372`;
  Universal artifact `9917002168` has digest
  `sha256:4c106115a9195c54008236d9ad25d11baea768890adc9806f3b2679d32e52c7e`.
  This closes the independently executed `.7` candidate checkpoint, not Qingshan
  promotion, real-provider verification, paid-provider QA or SOP-07.
- Product commit `3000920f78d7e0d2446f0c99eb8264be6c975762`, GitHub CI run
  `33822968508`: Nalu independently checked out the newer Qingshan
  `v2026.09.03.8` at exact commit `207ee38b18a635b200e0dbdba0815cafbd73ee28`.
  The `.7` to `.8` diff contains only 23 lines in the video-prompt compiler and its
  test; it does not change the public package or portable manifest. The independent
  audit recomputed tracked-tree SHA-256
  `dc432d79633511e4ddae6f7b6adc2560b91efc140fba8ae199f86494645d5250`,
  unchanged registry SHA-256
  `0b7d478904638f0d9e22452971b7aa8d95b9e7445355b53e364ff187fd0613a4`
  and unchanged portable-manifest SHA-256
  `61db4eeaad2f26643713f38e0c9ebaedf6bea952e8a8305661d8ae9b8add676a`.
  Registry and Writer-v2 checks remain `PASS` at 69 gates, 66 coded gates and 66
  runtime bindings. With credential-like variables stripped, all 33 registered portable
  modules ran: 209 tests passed with one declared skip, and six Writer tests passed.
  Public-interface status remains `FAIL` because package/CLI `0.3.0` still disagrees
  with portable manifest `0.3.1`; `.8` therefore replaces `.7` only as the latest
  reviewed quarantine record, not as Nalu's active production pin or paid authority.
  Runtime, Apple Silicon, Intel and Universal CI jobs all passed. Universal artifact
  `9919040824` has GitHub digest
  `sha256:63e2dfe13afc1e5ff84af4ddf86c19a41e2774ab043757f3f454c1322dcaedc8`.
  This closes the `.8` discovery/reproduction checkpoint, not promotion or SOP-07.
- Product commit `8597ad02ee4f091c98a97fd4479a66d630481989`, GitHub CI run
  `33824616662`: Nalu productizes `.8`'s safe provider-prompt finding independently
  while leaving the release quarantined. Compiler contract version 1.5.0 requires the
  exact rendered prompt and declares an inclusive 10,000-rune maximum. The single
  durable paid-task boundary recomputes that length immediately before any provider
  transport; a 10,001-rune prompt fails with zero transport calls while an exact
  10,000-rune prompt is accepted by the deterministic idempotent fixture. All 193
  Runtime tests and the Runtime, Apple Silicon, Intel and Universal CI jobs passed
  (jobs `100874565305`, `100874565474`, `100874565488`, `100875506187`). Universal
  artifact `9919607848` has GitHub digest
  `sha256:5ba5f5bc3a0a0de95fc2357548104385a85f081014ddb7a832a957ea0eaa319a`.
  No provider call or paid action occurred. This closes the prompt-rune preflight
  checkpoint, not Qingshan promotion, real-provider QA or SOP-07.
- Product commit `474d1d0cf19e0f6df642317e065f7017507dbf9a`, GitHub CI run
  `33842897568`: release discovery confirmed that `v2026.09.03.8` remains the newest
  upstream release and requires no duplicate review. The human upgrade SOP now names
  the same exact release and commit as the machine candidate record, replaces its stale
  `.4` description with the executed `.8` registry/Writer/public-interface evidence,
  and is checked by CI so documentation drift fails closed. The candidate remains
  quarantined solely because package/CLI `0.3.0` disagrees with portable manifest
  `0.3.1`; no pin, credential, provider request or paid authority changed. CI passed 197
  Runtime tests, the isolated 209-test registered candidate suite plus six Writer tests,
  both architecture Swift suites and builds, bundled-Runtime smoke, staged update,
  populated rollback and Universal merge. Runtime QA artifact `9925541416` has digest
  `sha256:99af642792ec604ea449cdeb4c6d1cda1ab1672dc91e53737ceb8b148e9f0240`;
  Universal artifact `9925617047` has digest
  `sha256:10c10cdbb9b96a035f87b5e321c87eef958b41c0e63865f00c0884ba36363f4d`.
  This closes only the current discovery/document-consistency checkpoint.
- On 2026-09-04, the credential-free latest-release check was repeated after commit
  `5c1feec`: GitHub still reports `v2026.09.03.8` as the latest release, matching the
  exact reviewed candidate `207ee38b18a635b200e0dbdba0815cafbd73ee28`, so no new
  candidate checkout or duplicate promotion review was created. The active pin remains
  `v2026.08.29.1`; `.8` remains quarantined for its `0.3.0` package/CLI versus `0.3.1`
  portable-manifest mismatch. This is current no-change discovery evidence only, not a
  promotion or provider-execution claim.
- Product commit `3af5ff35ab8be65d1ddaa41ee09f3b287e21600a`, GitHub CI run
  `33874201552`: Qingshan workspace materialization now builds into a private fixed-name
  staging directory, verifies the manifest package binding, complete declared file
  inventory, safe paths and exact digests, rejects links and non-regular members, and
  durably syncs the entire tree before publication. Promotion preserves the preceding
  complete workspace until the new tree is ready and syncs the workspace parent after
  every rename. Automated restart QA exercised both process-exit windows: after retiring
  the previous workspace and after promoting the replacement. Recovery exposed no
  partial public workspace, restored or retained one package-bound complete tree, removed
  all pending/previous remnants, and finished with a passing execution preflight. All
  268 Runtime tests and the Runtime, Apple Silicon, Intel and Universal jobs passed,
  including bundled-Runtime smoke, project isolation, staged update, populated rollback
  and controlled-evolution checks. Runtime QA artifact `9937263367` has digest
  `sha256:ce67c1889aa57a25050919f45c3e94b5753ac315fc9acad3d352140b736a0054`;
  Universal artifact `9937517494` has digest
  `sha256:315ba4b84575f79111d7c6a8411d7e477ba0a275d325f7d8c3276149e6f7c1c7`.
  This closes the deterministic workspace-publication crash boundary only; it does not
  correct the quarantined upstream release or claim real-provider or paid-task QA.
- Product commit `29d342a8abb911f464774dcf6f100d21865ffd88`, GitHub CI run
  `33875530606`: the Qingshan preflight report now uses an exclusive private staging
  file, complete-write and file sync, atomic replacement, and parent-directory sync.
  Unsafe public or staging paths fail closed. Automated restart QA interrupted the
  process after the replacement report became durable but remained private and again
  after it became public. The first window retained the preceding complete public
  report and a complete package-bound private replacement; the second exposed only the
  complete replacement. A fresh Runtime then removed the abandoned staging file and
  regenerated one valid `PASS` report bound to the same package digest. All 269 Runtime
  tests and the Runtime, Apple Silicon, Intel and Universal CI jobs passed, including
  bundled-Runtime smoke, project isolation, staged update, populated rollback and
  controlled-evolution checks. Runtime QA artifact `9937766365` has digest
  `sha256:7fc08e2152fc9f6de738e2ba0aba1080e5a79852cac5bc9017ec9d233e2a90a5`;
  Universal artifact `9937962005` has digest
  `sha256:5ac14be7076abeec8b5236f4c421d89dd77fd45f22b339274a9901f0f4d8d6f8`.
  This closes the deterministic preflight-report crash boundary only; it does not
  correct the quarantined upstream release or claim real-provider or paid-task QA.
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
- Commit `a45c63a75572d215ba2331bf91cc680c0b66d233`, GitHub CI run
  `33866004764`, Runtime QA artifact `9934050559` and Universal artifact
  `9934183476` (artifact digest
  `sha256:f484cc152c50b8a93b7247d18b43bfdfd6e75998e3e3730dcd38a7b7ba3383c0`):
  ordered run-event insertion now rechecks the production run under the same SQLite
  write lock used to allocate and insert the next sequence. A run deleted after stale
  preflight returns not-found rather than leaking a foreign-key error and leaves no
  event; concurrent writers still retain unique contiguous sequences. CI passed 255
  Runtime tests, both native Swift suites and architecture builds, Universal merge,
  bundled smoke, packaged project-isolation, staged-update and rollback QA. This closes
  the deterministic run-event deletion boundary, not authorized provider crash testing.
- Commit `1331d3cf4a1d4da72ce9f6a0ef7d107b55730f00`, GitHub CI run
  `33866987329`, Runtime QA artifact `9934417886` and Universal artifact
  `9934578076` (artifact digest
  `sha256:87f0c5374a2bc117453040a11d0a5eb949943c77d5c6038acf03ed0cb37851de`):
  cancellation and resume now commit the run status and its ordered audit event in one
  SQLite transaction bound to the exact preflight status. Event-insert failpoints prove
  both status changes roll back instead of leaving an eventless state; two concurrent
  cancellations produce one successful state/event pair and one conflict. CI passed
  258 Runtime tests, both native Swift suites and architecture builds, Universal merge,
  bundled smoke, packaged project-isolation, staged-update and rollback QA. This closes
  the deterministic cancellation/resume atomicity checkpoint, not real provider crash QA.
- Commit `55791658a8d20dce0b72c2deca55000daa47a4b9`, GitHub CI run
  `33868270489`, Runtime QA artifact `9934902326` and Universal artifact
  `9935035998` (artifact digest
  `sha256:4d097894f4fbf7185b4e52232239b126a9204882f439f6f030b20c85bafc40ff`):
  a successful Qingshan preflight now commits the production-run row, immutable asset
  bindings, initial ordered run event, episode transition and episode event, plus the
  idempotent-operation completion in one SQLite write transaction. The commit rechecks
  the exact approved script revision and current biometric/guardian consent under the
  write lock. A late episode-event failpoint proves all preceding writes roll back
  together, and a consent-revocation race creates no run or snapshot. CI passed 260
  Runtime tests, both native Swift suites and architecture builds, Universal merge,
  bundled smoke, packaged project-isolation, staged-update and rollback QA. This closes
  the deterministic database commit boundary; package-directory crash recovery and real
  provider crash QA remain open.
- Commit `a073744f119663c10e4816e0d54830a9d82c1faa`, GitHub CI run
  `33869392909`, Runtime QA artifact `9935439856` and Universal artifact
  `9935498519` (artifact digest
  `sha256:d50ecf03dad173eb157fd55996aa59b5ac8ae4fb7eadcba36362aa9181b19d47`):
  production start now holds a per-episode advisory operation lock across filesystem
  materialization, Qingshan preflight and the atomic database commit. After a simulated
  process crash, a fresh Runtime instance recovers the same pending idempotent request,
  reuses the exact run ID and immutable package digest, deterministically rematerializes
  its workspace and commits once. A concurrent live request cannot steal the lock, while
  a tampered recovery package is preserved and quarantined instead of overwritten. CI
  passed 263 Runtime tests, both native Swift suites and architecture builds, Universal
  merge, bundled smoke, packaged project-isolation, staged-update and rollback QA. This
  closes the deterministic package/database crash boundary for explicitly idempotent
  starts; provider crash QA and crash recovery for a dry-run without a client key remain
  open.
- Commit `b861af0b9217c91bc7ceed1b7f4d7aa3119da168`, GitHub CI run
  `33870562505`, Runtime QA artifact `9935781789` and Universal artifact
  `9935937900` (artifact digest
  `sha256:41f70e5fefa246af996a371b91b32a165ba4cddab7083afad8428e6db1b26f46`):
  every keyless dry-run now receives a stable server-side request identity before any
  package filesystem mutation. Normal retries replay the one committed run, while a
  simulated process crash is recovered by a fresh Runtime with the exact pending run ID
  and package digest. The public contract documents that paid production still requires
  a caller-supplied key; that gate is unchanged and executes before the internal dry-run
  identity is assigned. CI passed 265 Runtime tests, both native Swift suites and
  architecture builds, Universal merge, bundled smoke, packaged project-isolation,
  staged-update and rollback QA. This closes the remaining deterministic keyless
  preflight crash gap, not authorized provider crash testing.
- Commit `d4a93fc64ac602458cd656e5c7dcaea5613f26cb`, GitHub CI run
  `33871628686`, Runtime QA artifact `9936347951` and Universal artifact
  `9936502837` (artifact digest
  `sha256:cac0a9e3fde1e4a74ca0485a5d847940ba088e090a5fcd48723b4dd491780f98`):
  the immutable production package is now created as a mode-`0600`, exclusive,
  no-follow staging file, flushed and file-synced before atomic promotion; the final
  directory entry is then directory-synced. A simulated crash after the complete
  staging file was synced but before promotion is recovered by a fresh Runtime using
  the same run ID and package digest, with exactly one run row and initial event.
  Changed staged evidence is preserved and quarantined without creating a run or
  overwriting either file. CI passed 267 Runtime tests, both native Swift suites and
  architecture builds, Universal merge, bundled smoke, packaged project isolation,
  staged-update, rollback and controlled-evolution verification. This closes the
  deterministic production-package write/promotion boundary, not authorized provider
  crash testing or signed-app human QA.
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
- Commit `1fb6757` removes client assertions as semantic-ASR release authority. The
  Runtime now requires a registered local recognizer execution against the exact sealed
  master, independently fingerprints its decoded audio, hashes the recognizer executable
  and complete timestamped output, and stores a nested canonical execution digest inside
  the immutable QA report. Missing recognizers, mismatched client claims, different
  master/audio, invalid executable digests and any network-used execution fail closed.
  Stored reports are revalidated against the current sealed master; even an attacker who
  recomputes both the nested and outer report digests cannot turn network recognition or
  a different audio fingerprint into release evidence. Old `/v1` response consumers
  remain schema-compatible, while old reports without execution evidence cannot authorize
  completion or release. All 130 Runtime tests, lint, OpenAPI freshness/backward
  compatibility, real HTTP smoke, SOP/progress audits, Swift tests, independent arm64 and
  x86_64 builds/smokes, and universal merge passed in GitHub CI run `33506251878`
  (jobs `99850917149`, `99850917480`, `99850917671`, `99852261808`).
- Exact universal artifact `9799897045` has GitHub digest
  `48d4a3002c0914880cc7697cf63c9dbbc37a59dcc2e854a071978fff984f66e7` and inner ZIP
  SHA-256 `3b3119eaffe3abc0d657295ee593ddd3b74fa0e71b0339cabd10dcb2f859872f`.
  Its bundled Runtime SHA-256 is
  `753811281d8525acdacb060cedd6b8c61f07038e5399ca7828b44d839501da45`, contains both
  arm64 and x86_64 slices, and its recursive PyInstaller archive lists
  `nalu_runtime.semantic_recognizer`, `nalu_runtime.engine` and `nalu_runtime.app`.
  The downloaded application was not launched because user confirmation for executing
  newly downloaded software remains pending. This closes only the untrusted-provenance
  checkpoint: a packaged production Apple on-device recognizer, real-master semantic QA
  and original-resolution human audiovisual review remain required for SOP-09 `PASS`.
- Commits `f56c5e8`, `41fc9aa` and `ad39da1` add that packaged production recognizer
  boundary. A separately built Swift helper rehashes the sealed master before and after
  `SFSpeechURLRecognitionRequest`, requires Apple on-device Simplified Chinese support,
  explicitly disables network fallback and returns timestamped segments through a
  bounded JSON protocol. The Runtime launches it with a minimal environment, hashes the
  helper before and after execution, validates finite bounded segment evidence, computes
  the decoded-audio fingerprint itself and treats the helper output—not compatible legacy
  client fields—as QA authority. The app registers only its packaged helper path. Build,
  universal merge, ad-hoc and production signing paths explicitly preserve the Speech
  entitlement on the nested executable; release verification reads that entitlement and
  checks both architectures. Bundle smoke executes a malformed-input negative case and
  requires the helper to exit closed before requesting Speech permission.
- Final implementation candidate `ad39da1` passed all 131 Runtime tests, lint, OpenAPI,
  SOP/progress/Qingshan gates, real HTTP smoke, Swift Package tests, independent arm64 and
  x86_64 application builds, helper entitlement/release verification, bundled Runtime
  smokes, staged update, populated rollback and universal merge in GitHub CI run
  `33508561436` (jobs `99858502449`, `99858502773`, `99858502788`, `99860080790`).
  Exact universal artifact `9800868404` has GitHub digest
  `48a7c829c84e55e13e05ecf8979cbdb337927a9cf89972a6273758570e36184b`; its inner ZIP
  SHA-256 is `cd391cfb898dd6b3e86e5e1f95a9d84ddfda55c1824ee1a4a5c283ac62e9f1eb`.
  Independent extraction found helper SHA-256
  `343373e59ad444a2604fcfa0fd0046be382478e17434a8893982857258ea09dc`, both `arm64`
  and `x86_64` slices, a valid nested signature, Speech and audio-input entitlements, and
  the on-device/no-network protocol strings. No downloaded code was launched on the
  user's Mac because confirmation remains pending. This closes the packaged recognizer
  implementation checkpoint, not SOP-09: real Speech permission, real consented final-
  master recognition, calibrated semantic acceptance and human audiovisual review on one
  release candidate are still required.
- Commit `a53c3edefe2944511f0592fc1429d85351c43077`, GitHub CI run
  `33694643341`: postproduction lineage QA now re-decodes each selected provider source
  and independently compares its measured duration with the sealed declaration and
  editorial in/out points. Missing `EXPLICIT_SOURCE_WINDOW` authority, duration mismatch,
  out-of-range selection and whole-provider-media passthrough are release-blocking even
  if a forged manifest recomputes its own digest. All 151 Runtime tests, HTTP/offline E2E,
  Swift tests, arm64, Intel and Universal builds, bundle smoke, staged update and rollback
  passed. Universal artifact `9871483785` has GitHub digest
  `sha256:7f8d755e47ec5c82c933f1ecccb52c79ce3c260cd2093160d38979b5296995ea`.
  This closes the editorial-authority QA checkpoint, not SOP-09 or whole-product QA.
- Product commit `25e66fb97158c199bd5fc4688a4c813d5377ed83`, GitHub CI run
  `33845612268`: packaged postproduction QA no longer trusts a caller-supplied release
  hash. Both release-bundle harnesses require the downloaded ZIP, recompute its SHA-256
  before launching Runtime and reject malformed artifact/commit identities. Restart
  replay is an explicit operation instead of an accidental duration side effect; soak
  fixtures use bounded source media and prove their editorial windows cover the target
  timeline without whole-provider-media passthrough. Eight direct integrity/layout tests
  were added. CI passed 205 Runtime tests, the complete isolated Qingshan contract,
  both architecture Swift suites and builds, bundle smoke, staged update, populated
  rollback and Universal merge. Universal artifact `9926536313` has GitHub digest
  `sha256:48e8cd1cf4957adf9af6d3bacbea46863099dfd40defe69d176247911f76e1e9`;
  its independently downloaded inner ZIP SHA-256 is
  `1c4716af74bacd16c3e763ae5e34e7331eef473937f5f6e54d08fe1346d0e8b2`.
  The strengthened harness ran that exact artifact over loopback HTTP, materialized two
  ordered shots and all five audio layers, sealed lineage, rejected a tampered source,
  stopped, restarted, rehashed every result and preserved exactly one materialization
  event; evidence report SHA-256 is
  `e137a03233bb5174ebf6ccf3771be347ab12e45f9d26c008c44965449e974623`.
  The same artifact separately proved confirmed character/prop inputs `READY`, missing
  held-prop authority `BLOCKED` and provider upload disabled; evidence report SHA-256 is
  `ae1f65d0a0f6fd0a573f43b3f8e7fa46f8b7eea0660bc130a6856e52e7974d91`.
  Synthetic perceptual analysis remained `FAIL` and is not claimed as visual or human
  acceptance. This closes only the current automated packaged-evidence checkpoint.
- Product commit `6e1a98f8103fdc61c989b8c25b0507f5c41773a6` and contract-preserving
  commit `79fdb4d912c9407c201de634a2d78111d9ea72df`, GitHub CI run
  `33873288043`, Runtime QA artifact `9936868298` and Universal artifact
  `9937001457` (artifact digest
  `sha256:647d33e09a489b86a79179b74ee9d7d935b710b94d80eab4d7d8c35c3359bf7e`):
  completed postproduction files and directories are now flushed and synced before the
  staging tree is atomically promoted, and the containing directory is synced before the
  result is exposed. A simulated process exit immediately after durable promotion leaves
  exactly one complete result; a fresh Runtime verifies and reuses it, survives a second
  failure before SQLite state commit, and finally records one materialization event
  without re-encoding or duplicating output. The established SOP-12 scenario test node
  remains stable. CI passed 267 Runtime tests, the independently verified offline
  seven-scenario rehearsal, both native Swift suites and architecture builds, Universal
  merge, bundled smoke, project isolation, staged-update, rollback and controlled-
  evolution verification. This closes the deterministic postproduction tree durability
  boundary, not real-master Apple Speech or original-resolution human audiovisual QA.
- Product commit `3d7c9b060c59cd15a0e2f00872e20f796ab17577`, GitHub CI run
  `33878943656`: rendered-output seals, local visual-analysis results and their generated
  continuity manifests now share one exclusive durable publication primitive. Each artifact
  is written through a private no-follow/no-replace file, flushed and synced, hard-linked
  without replacing concurrent evidence, and has both directory-entry publication and
  temporary-file cleanup synced before the caller can bind a SQLite event. Direct tests
  observed file and directory syncs, reopened and rehashed the acknowledged bytes, and proved
  a competing publication cannot replace the first artifact or leave hidden temporary files.
  The existing visual-analysis crash-boundary fixture still proved a durable result can be
  recovered into exactly one SQLite event without rerunning the analyzer. All 273 Runtime
  tests and the Runtime, Apple Silicon, Intel and Universal jobs passed, including bundled-
  Runtime smoke, project isolation, staged update, populated rollback and controlled-
  evolution checks. Runtime QA artifact `9939251031` has digest
  `sha256:b81cac2f39c0445aaf2d9bfe4aff8cf5a57bf50417766bcf82c11f4c6040c339`;
  Universal artifact `9939249573` has digest
  `sha256:cffdb4e16d5650a46a91151056c90a984d5dcaa6f3ef067c455a61be8bdd8b12`.
  This closes the deterministic postproduction-evidence filesystem durability checkpoint,
  not the remaining seal-event crash recovery, real-master Apple Speech or original-
  resolution human audiovisual QA.
- Product commit `ccbca3b3ab0af19d9d892fc95d8f77fa33462111`, GitHub CI run
  `33880047560`: the rendered-output sealing transaction now recovers the exact file/SQLite
  boundary. If the process exits after the durable seal is published but before its audit
  event commits, a retry after Runtime restart revalidates the seal's own digest, run,
  project, episode, immutable production package, resolved library, Qingshan workspace,
  operator and every current artifact byte before atomically recording the missing event.
  A changed master was rejected without creating an event; restoring the original bytes
  recovered the existing seal byte-for-byte and produced exactly one event, while a normal
  duplicate remained a conflict. All 274 Runtime tests and the Runtime, Apple Silicon,
  Intel and Universal jobs passed, including bundled-Runtime smoke, project isolation,
  staged update, populated rollback and controlled-evolution checks. Runtime QA artifact
  `9939547829` has digest
  `sha256:2b3927676b7641dc3c7a107db5c3dede281119d14514ef4a6be611fc0b956f4e`;
  Universal artifact `9939815153` has digest
  `sha256:8334731eeab1ca8522fa524d12179dd3df689ac35faa2b895d9d191326a4bef4`.
  This closes the deterministic rendered-output seal/event crash boundary, not the
  remaining mutable-report durability, real-master Apple Speech or original-resolution
  human audiovisual QA.
- Product commit `2b03e5eddae388cc6eb17e84ec1797728c1afac1`, GitHub CI run
  `33881338870`: every SOP-09 repair plan and release-blocking QA report now reaches disk
  durably before its SQLite audit event is attempted. Mutable repair, container-structure
  and decoded-media reports use a synced private file, atomic replacement and parent-
  directory sync; immutable lineage, visual-continuity and semantic reports use the same
  synced exclusive-create primitive as output seals. Direct QA observed exact reopened
  bytes and digests, verified file plus directory sync, and forced replacement failure to
  prove the prior report remains intact with no hidden temporary file. All 276 Runtime
  tests and the Runtime, Apple Silicon, Intel and Universal jobs passed, including bundled-
  Runtime smoke, project isolation, staged update, populated rollback and controlled-
  evolution checks. Runtime QA artifact `9940073541` has digest
  `sha256:9172f992fd9f598c50ba21216a6514b48b99ea59242d33e89d3c1b25b8736a98`;
  Universal artifact `9940158198` has digest
  `sha256:4f380db4a6c420ed5b6b79a9359f5f93ee5b19a1fad33b6907e1b18fca6ebf92`.
  This closes the deterministic SOP-09 QA-report filesystem durability checkpoint, not
  missing-event recovery, real-master Apple Speech or original-resolution human QA.
- Product commit `4a50ad21aadd670a2517db3438d7579dc759633f`, GitHub CI run
  `33882498857`: SOP-09 report events are now idempotently bound to the exact durable
  report or repair-plan digest. After a process exit between report publication and event
  commit, replay reads and verifies the existing bytes and restores the missing event;
  another replay returns the same event rather than duplicating it. The transactional
  event primitive permits a genuinely changed mutable report to create a later event but
  rejects any call whose dedupe digest differs from its payload. A real container-QA
  crash/restart fixture proved the report bytes and SHA-256 remained unchanged and exactly
  one event survived. All 277 Runtime tests and the Runtime, Apple Silicon, Intel and
  Universal jobs passed, including bundled-Runtime smoke, project isolation, staged
  update, populated rollback and controlled-evolution checks. Runtime QA artifact
  `9940544752` has digest
  `sha256:aebe45b3790a539b18e84ad51b0c6c4172586788a9749849f7c38fd88c63b8cc`;
  Universal artifact `9940783454` has digest
  `sha256:8c648be61ef2cb0d105461c1d228944cf52c0fa0151cb80f76beef34cb0b92dc`.
  This closes the deterministic SOP-09 report/event crash boundary, not downstream repair-
  plan recovery, real-master Apple Speech or original-resolution human QA.
- Product commit `d94a85ec47ee27293317a74e799ace41fdac6d06`, GitHub CI run
  `33883847784`: every replayed failed container-structure, decoded-media, lineage,
  visual-continuity or semantic QA result now continues through the repair derivation
  boundary after verifying its durable report. A crash/restart integration fixture exits
  after the failed media report and its digest-bound event have committed but before the
  repair plan is written; restart preserves the exact report bytes, reconstructs the
  `mp4_structure` task, and leaves exactly one report event and one repair-plan event.
  Passing reports remain unchanged, while conflicting immutable evidence still fails
  closed. All 278 Runtime tests and the Runtime, Apple Silicon, Intel and Universal jobs
  passed, including bundled-Runtime smoke, project isolation, staged update, populated
  rollback and controlled-evolution checks. Runtime QA artifact `9941087635` has digest
  `sha256:40883793c53a308229806dc915ec269eb71326e4c51aedcc012b36c76f39a3d2`;
  Universal artifact `9941335109` has digest
  `sha256:fcbd9d046b74153f5bc8cb5669ed0ac9c96114e2331d6a6a71cea3f628091e81`.
  This closes deterministic downstream repair-plan recovery after a report/event crash,
  not real-master Apple Speech, original-resolution human audiovisual QA or SOP-09.

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
- Commit `210b5c7` adds a default-disabled publication-learning verifier boundary,
  SQLite migration 24, immutable platform publication identities and metric snapshots,
  stable idempotency protection, exact-replay handling, child guardian enforcement and
  monotonically versioned next-episode director strategies. The strategy is advisory:
  it cannot edit an approved script, start production, spend credits or publish.
  Automated cases cover disabled/incorrect verifiers, identity substitution, duplicate
  and replacement remote IDs, malformed metric windows, changed replays, restart
  persistence and two-platform child-project consent. All 116 Runtime tests, lint,
  OpenAPI compatibility, SOP/progress audits and real loopback HTTP smoke passed in
  GitHub CI run `33493012088`, together with Apple Silicon, Intel and Universal macOS
  builds, bundled-Runtime smoke, staged-update and rollback rehearsals.
- The exact Universal artifact `9794733903` has GitHub artifact digest
  `31f4610cdc6a2f27af8fd4ffbd46274b54849b29e33039c187ed54c838d5132a`.
  A fresh repository-external download passed a complete ZIP integrity scan and had
  inner ZIP SHA-256
  `2940066f530c36f8e4a2018f853d52d527b61f4a2256ab894adca82e09cb52b3`;
  the staged-update and rollback evidence files had SHA-256 values
  `1c761b37048d8588974222efc5323002caebebf32cc461ead7138eb5dcdb2972`
  and `81afb3489f307734fedd41cb60aef52e91ef27d26119f3b47e9610096bf95e52`.
  Independent extraction, strict deep signature verification and the Universal release
  verifier passed; both the native executable and bundled Runtime contain arm64 and
  x86_64 slices. The signature remains ad hoc, not Developer ID or notarization evidence.
- This closes the local publication-identity/metrics/strategy checkpoint, not SOP-10.
  No real provider lookup, publication, account write or paid call was performed. Still
  required before `PASS`: explicit user-authorized real platform accounts, test-channel
  publication and identity/metrics reconciliation against those remote systems on the
  same signed and notarized candidate. Dry-run or local verifier evidence is not a
  publication claim.
- Commit `6a68892` evolves portable project export to v20. It preserves only the
  completed production-source rows needed by the project’s publication identities,
  immutable metric snapshots and complete director-strategy revision history. Import
  verifies every inner digest and project/run/episode linkage before one atomic
  transaction, rejects cross-project data and recomputed outer-envelope tampering, and
  remaps stale old-machine production paths beneath the new local data root. A dedicated
  v19 downgrade/restore case proves earlier backups remain accepted without the new
  tables. All 116 Runtime tests, lint, OpenAPI compatibility, real HTTP smoke, SOP and
  progress audits passed in GitHub CI run `33494844711`; Apple Silicon, Intel and
  Universal builds, bundled-Runtime smoke, staged update and populated rollback also
  passed.
- The exact Universal artifact `9795485341` has GitHub artifact digest
  `3bcde6e190bab8e1b7f992885b108560040d6518faf4f7eb01f585f4755ef72f`.
  A fresh independent download passed a complete ZIP integrity scan and had inner ZIP
  SHA-256 `698a57930564f1fb7cbdf246f8128bf4ed312569fe7213067392291528af9485`;
  staged-update and rollback evidence-file SHA-256 values were
  `f4d1812efdc2193c1a1bbf7df6bd012013fd06fb8ac6b8d160b03f48e36777a6`
  and `9849a6abdf73de75195d88b0427af83b7abd62caeb86bc61d11eb9e95317003e`.
  Independent extraction, strict deep signature verification and the Universal release
  verifier passed. The native executable and bundled Runtime both contain arm64 and
  x86_64 slices; the Runtime SHA-256 is
  `035e43b8e1afbfa31791ca4519b2774f74eb9020d7438769875232ad58b2e610`.
  This is ad-hoc signature evidence, not Developer ID or notarization evidence, and
  closes the portable-learning-state checkpoint rather than SOP-10.
- Commits `4486b8a` and `d3537f2` add the native read-only publication-learning
  presentation. The macOS client digest-checks the project, metric snapshot and strategy
  linkage, rejects any record that claims a publish, production or external-write action,
  and translates the verified window into large-text views, completion, observations and
  versioned next-episode advice. It offers readback and refresh only: there is no metrics
  form, apply button, production trigger or publish control. The first CI attempt
  (`33496459840`) exposed and rejected a SwiftUI style-inference compile failure; the
  concrete-color fix then passed all 116 Runtime tests, 46 XCTest cases, 26 Swift Testing
  cases, real HTTP smoke, Apple Silicon, Intel and Universal builds, bundled-Runtime
  smoke, staged update and populated rollback in CI run `33496733695`.
- The exact Universal artifact `9796228956` has GitHub artifact digest
  `ced3e47da2b5c3b732e84f2940a0210834042502298d67fea113df28b97fe391`.
  A fresh independent download passed a complete ZIP integrity scan and had inner ZIP
  SHA-256 `b96840cfbacfc1fa108cf6b7db02b90bbc64f1b6b1455f53aa5cc9d2c3716035`;
  staged-update and rollback evidence-file SHA-256 values were
  `4104dc026d9200debbbf2c7c1c4a28e7af601ed5a507de9bb34cae33ad551ba9`
  and `4e1a8c67d041344cc69b7ba4d52c2beb8c4ce53382061cc596a06cffa8606ca7`.
  Independent extraction, strict deep signature verification and the Universal release
  verifier passed; the native executable and bundled Runtime contain both architectures,
  and the Runtime SHA-256 is
  `8932965c0d56a47428c4ec0cec1820bfa178c12def64cfbd447bbafc7525805d`.
  This records automated native-build evidence only. It does not replace an actual-window
  large-text/readback/VoiceOver check with a populated learning fixture, Developer ID
  signing, notarization or authorized real-platform reconciliation, so this native
  presentation checkpoint and SOP-10 remain `IN_PROGRESS`.
- Commit `b4587a7` closes the deterministic native-client request checkpoint. An injected
  local `URLProtocol` fixture proves that the macOS client first lists the selected
  project's strategy revisions, then fetches the digest-bound metric snapshot, and
  refuses an external-write claim or a mismatched metric digest. The default production
  `URLSession` path is unchanged. All 116 Runtime tests, 46 XCTest cases and 27 Swift
  Testing cases passed with Apple Silicon, Intel and Universal builds, bundled-Runtime
  smoke, staged update and populated rollback in CI run `33497842560`; the new
  `nativeClientLoadsBothReadOnlyEndpointsAndFailsClosed` case passed explicitly.
- Universal artifact `9796643058` has GitHub artifact digest
  `b8e3ce07307c970d9266b1d68ee6aeeeef79ec9213f0a28ab254ca1912cbcf99`.
  A fresh independent download passed a complete ZIP integrity scan and had inner ZIP
  SHA-256 `8e01d54a0f7ca6d5106b6e76c4d81d37016eb9e39c793af52b22a4e12e2ada7b`;
  staged-update and rollback evidence-file SHA-256 values were
  `8240f3c7ba1611e432960c307d2423bc404f91ef9d6bbcb60539769f147186cb`
  and `530df6f871bbd874492031fe5d74a6bb96e70d196e34ef5d8388109e249350c7`.
  Both reports say `PASS` and explicitly limit scope to offline/loopback work without
  providers, paid calls or publication. Independent extraction, strict deep signature
  verification and the Universal release verifier passed; the native executable,
  bundled Runtime and visual analyzer contain arm64 and x86_64 slices. Their first two
  SHA-256 values are respectively
  `be6c15e7f8e05a0231914cc6bfdb6e7dc3589053123c892fdecfbae4aaaec16e`
  and `f34309a3f72d55ec9fc046fc20c77849549980f8be9ebef336ce2ac173e7a806`.
  This closes only the native request/integrity checkpoint. Actual-window populated-data
  accessibility QA, authorized platform evidence, Developer ID signing and notarization
  remain missing, so SOP-10 remains `IN_PROGRESS`.
- Commit `201e879` adds a temporary-directory-only native-window fixture boundary. The
  generator refuses non-empty or non-temporary roots, creates one isolated SQLite
  project with two episodes and digest-valid read-only metrics/advice, and records that
  no production data, provider, paid call or publication was touched. The native app
  accepts that root only behind an exact explicit QA flag, requires an existing resolved
  temporary directory, rejects a running unrelated loopback Runtime, and otherwise keeps
  the normal Application Support path. Local full Runtime regression passed 118 tests;
  GitHub CI run `33499198671` passed the same 118 tests, 48 XCTest cases, 27 Swift
  Testing cases, both architecture builds, Universal merge, bundle smoke, staged update
  and populated rollback. The two new Swift path-boundary tests passed explicitly.
- Universal artifact `9797143801` has GitHub artifact digest
  `440d89e3de891570b16654d1370cfcd0520ad40e71c3f15d8274905f6d161e3f`.
  A fresh independent download passed a complete ZIP integrity scan and had inner ZIP
  SHA-256 `8c99b744166622753489e96be95b8b7e395998e237e3aefd5078d1ba1d6c9134`;
  staged-update and rollback evidence-file SHA-256 values were
  `ff49d5cc703b5dc528104414ee5c1124d65410099e268ec243c7f00c48e376f0`
  and `23a840bd84a5610f03d6db064ecb66b2ebd4abda935c421f803941c0a1d91027`.
  Both reports say `PASS` with offline/loopback-only scope. Independent extraction,
  strict deep signature verification and the Universal release verifier passed; all
  three executables contain arm64 and x86_64 slices. Native executable and Runtime
  SHA-256 values are respectively
  `1a5bb009d38a8b69bfa7c1e0553dbf6fae09b6eabad18206c47800e14b6e6048`
  and `9138a6f95f51b3f27a746cc275501fbbc5b29dae4f185868b23e6f373fcd6721`.
  This closes the safe fixture-generation checkpoint, not the actual-window review:
  the downloaded app has not yet been launched, readback and VoiceOver have not been
  observed, and the signature is still ad hoc. SOP-10 remains `IN_PROGRESS`.
- Commit `6cbc13c` extends bundle smoke so the arm64, x86_64 and merged Universal
  candidates each create a fresh isolated publication-learning database, boot their own
  embedded Runtime, fetch project/strategy/metrics over loopback, verify the stored
  digest link and assert every no-write/no-production/no-publication flag. CI run
  `33500024374` passed all three packaged smoke executions plus 118 Runtime tests, 48
  XCTest cases, 27 Swift Testing cases, build, update and rollback gates. The Universal
  `nalu.packaged-publication-learning-qa/v1` report is `PASS`; its SHA-256 is
  `50e55480f970ebbb7d652d60aaa6944508b02cb353c1adbf127a51714a9c2fa9`
  and its internal canonical report digest is
  `0c9f27711f48e8813566bf06a97a84a3bc584229bec52908b5db971a5d2fda9a`.
- Universal artifact `9797507392` has GitHub artifact digest
  `794f6ff7e609985a34ef73d0e8ef449263c95429532dfd070d5b822b5dc61400`.
  A fresh independent download passed ZIP integrity with inner ZIP SHA-256
  `7d680fb2f418755eaa8e4d77b6b05486fc0d191cbceb8a8edbfd4c9d8895487f`;
  staged-update and rollback evidence SHA-256 values were
  `19541b3e5f6f6be9b30ea994d652b4b9848aaabb54691f8ffd7c7b3f88ec9c73`
  and `0ce08e0d5e6f301fc3a3e9d9bbb96a7bd7043f071c3dced7d2100aeca6728b0f`.
  Independent extraction, Universal release verification and strict deep signature
  verification passed; native executable and Runtime contain both architectures with
  SHA-256 values `4c9138a6d688b257b7e71a300f923ff1869365e51f3e6a7471dce117e25386ef`
  and `f600d6f95f1c74347e56a2abe27b9618cc282bc07a2ae1060d6947d86cb9b6eb`.
  The packaged fixture checkpoint is closed, but actual-window visual/readback/VoiceOver
  observation and Developer ID/notarization remain absent. SOP-10 stays `IN_PROGRESS`.
- Commit `fa0eee8` gives the publication-learning card a stable accessibility contract:
  unique identifiers cover the card, metrics, observations, directives, readback,
  refresh and safety statement; combined Chinese labels preserve visible order; metric
  and narrative text can grow vertically at larger sizes; refresh explicitly says it is
  read-only. The contract test checks coherent platform/window/views/completion/advice
  and no-write wording plus identifier uniqueness. CI run `33500996286` passed 118
  Runtime tests, 48 XCTest cases and 28 Swift Testing cases (including the named new
  VoiceOver contract test), all architecture builds, packaged fixture smokes, Universal
  merge, staged update and rollback.
- Universal artifact `9798019635` has GitHub artifact digest
  `3ba26b8337d4213454f5e86a18ea3debde73ff064ef8520216d9ff39a096e86e`.
  A fresh independent download passed ZIP integrity with inner ZIP SHA-256
  `bc888d7e188e43c27bf02c6a390cb4dc805126294bc61c490ad9d1f3423a839a`;
  staged-update, rollback and packaged publication-fixture evidence SHA-256 values were
  `00c93b4acc4ea8026360db5cd7c76e3b3094c130134a43a195666a6cee673a9e`,
  `79c332281db66d02628d004351518a6a602af309b0aaa424e36990ae034df568`
  and `473ed0d45ef25c22527a0bbb1ac0d18bb4ffc32ebd21db2676bc737f0b5d31fa`.
  Independent extraction, strict deep signature and Universal release checks passed;
  native executable and Runtime SHA-256 values are
  `8ddca523d43dc5f4048495a27e7b8dac75225599e269a37a7ef83550bd692329`
  and `20004bb1e0198fcd3b5750fd5b0f3211107f50a4dcf8ead58793d85f52ed9d64`.
  An independent static binary scan found all seven exact accessibility identifiers.
  This closes the code-level accessibility contract only. The app has not been launched
  for actual-window visual/readback/VoiceOver observation, so SOP-10 remains
  `IN_PROGRESS`.
- Commit `e2c631a` promotes the seven stable publication-learning identifiers into the
  release verifier. Every arm64, x86_64 and Universal candidate now fails before signing
  acceptance if its native executable omits any identifier. CI run `33502330720` passed
  that gate for both architecture builds and the merged Universal candidate together
  with 118 Runtime tests, 48 XCTest cases, 28 Swift Testing cases, packaged-learning
  smoke, staged update and populated rollback.
- Universal artifact `9798500816` has GitHub artifact digest
  `6a4bcb1e57fc130ba66b9446f5d102a1de6ecba9ef734f93cfbb05320823d23f`.
  A fresh independent download passed complete ZIP integrity with inner ZIP SHA-256
  `8bf6f404b9768161f105476409d303d53bf8c864119f4fc7bb6b2377c520eff8`;
  staged-update, rollback and packaged-learning evidence SHA-256 values were
  `4a91c1b7e50c2662ae4be8eed7a3d65d19dca840726e90a7f9adb1bcb458ec99`,
  `b779abb74053da89051df7f957247039115aa5e7d2d4a7bbbc62526df8b2595c`
  and `ec405c22c4e8bd9b05b44d97379ee1246c58edc4e706d8eb7df7196fca220103`.
  The updated verifier passed independently with Universal enforcement and strict deep
  signature verification. Native executable and Runtime SHA-256 values are
  `c0c9c13b51cc0c67c19d2a978ac7ad11b0b22f2c740ad8e00a4f543652559051`
  and `55f1b155daf537ce8e6f82acf86edea5940c699f99dd368bd6c74f7f7b9d9953`.
  Static contract preservation is now a permanent release gate, but it still is not an
  actual VoiceOver/readback/layout observation. SOP-10 remains `IN_PROGRESS`.
- Product commits `4864976`, `8433ded` and `f2dfd40` close a packaged-app isolation
  regression found during native review. Every native `RuntimeClient` request now requires
  the current app to own a ready child Runtime; a denied second process sends no request,
  stops initial loading and presents the red “本地制片厂未连接 ×” state instead of attaching
  to another process's loopback server. The injected transport test proves the denied
  client makes zero `URLProtocol` requests. GitHub CI run `33821294202` on exact product
  commit `f2dfd40060e1bda300cd6f580f85b8d489d2f5ff` passed 191 Runtime tests, Swift tests,
  both architecture builds and the Universal build, bundle smoke, staged-update and
  populated rollback gates.
- Universal artifact `9918470084` has GitHub artifact digest
  `sha256:124d1450cbaf911ccbb727bbc0b400fcbb5477bbcd7f25172cea0dc0a32ad401`.
  A fresh repository-external download passed full extraction, strict deep ad-hoc
  signature validation and the Universal release verifier; its inner ZIP SHA-256 is
  `27103d7ffcbf123ce6528d130693321dc9d3ca247c6ae5fa4d1230ff844f0718`.
  On an Apple Silicon Mac, the exact downloaded app loaded an isolated completed fixture
  and exposed “发行身份已核验 · 只读”, “第 1 集 · 第一集 · 那张旧照片” and
  “100% · 制作完成”. Its actual accessibility tree contained the stable metrics,
  observations, directives and safety identifiers, plus a refresh button whose help says
  it only reads verified local records and a readback button whose help says it reads
  metrics, next-episode advice and safety guidance. A simultaneous second exact process
  spawned no Runtime and exposed no publication identity, episode or completion data.
  This is automated Accessibility API observation, not a human VoiceOver or audible
  readback acceptance, and no provider or publication action occurred; SOP-10 therefore
  remains `IN_PROGRESS`.
- Commit `7fad3c5a2c074bee6e40ef8fedfd41a7679e7260` replaces log-trust for the
  packaged publication-learning fixture with a reusable fail-closed verifier. It rejects
  duplicate or unexpected JSON fields, a changed canonical report digest, any failed
  safety flag, non-loopback scope, production-data mutation, unstable record identities,
  a substituted report or release ZIP, a malformed checksum manifest and an artifact
  archive whose bytes do not match GitHub's digest. The Universal CI job now verifies
  the report and release ZIP before upload and includes its canonical verification
  receipt. Four report-tampering cases plus artifact-digest, report-substitution and
  release-substitution negatives are permanent tests. GitHub CI run `33847084151`
  passed 211 Runtime tests, lint, contract/audit checks, real HTTP and offline E2E
  rehearsals, both architecture builds and the Universal build; packaged smoke,
  staged-update, rollback and the new verifier all passed.
- The exact Universal artifact `9927090722` has GitHub digest
  `sha256:eb732017ee31bd3d936dfc05ad581992d23458459ec59e8ec999d515d032dcea`.
  A repository-external download independently reproduced that digest, bound the sibling
  report and application ZIP byte-for-byte to the archive, and validated the archive's
  checksum manifest. The inner ZIP SHA-256 is
  `9f13d2b3c7135335def50a7769d4928591762e195d2b31677e8e4cd864afa91e`;
  the packaged report file SHA-256 is
  `eb01570eaf9ae90695f0cbb5ed6ea64d7d27df3d439837c42d2aa46ee9c33766`
  and its internal canonical digest is
  `74ac566531ce3879c441a62ecff0bd455b780343db1e6fdb574e3faa79db4d01`.
  The independently generated bound receipt file has SHA-256
  `bc5941ad497c8bfa06566ce51398f3002c545888791a9757c9d94bd7a615ca98`
  and canonical receipt digest
  `a6164452bba38dc722b9fc004a51e611bd53bc829d1401eea717cc8e81724418`.
  It explicitly records zero publication, paid calls and production-data mutation. This
  closes the packaged evidence-provenance checkpoint only: real platform authorization,
  publication/metrics reconciliation, human VoiceOver/readback acceptance, Developer ID
  signing and notarization remain absent, so SOP-10 remains `IN_PROGRESS`.
- Product commit `2687b50a34e4f95bd50023d6fee9deeca251ca17`, GitHub CI run
  `33885124622`: offline release packages and platform-specific publication dry-runs now
  use synced exclusive publication, so their private file bytes and parent-directory
  entry are durable before SQLite audit acknowledgement. The exact-replay paths bind the
  immutable manifest or plan digest to an idempotent event and restore a missing event
  after restart without rewriting the file or performing a network call. The integration
  fixture forced a process exit after each durable file but before its event commit,
  restarted the Runtime twice, verified byte-for-byte and SHA-256 stability, and observed
  exactly one recovered release-package event and one recovered dry-run event. Changed
  title or channel metadata remains conflict-blocked. All 278 Runtime tests and the
  Runtime, Apple Silicon, Intel and Universal jobs passed, including bundled-Runtime
  smoke, project isolation, staged update, populated rollback and controlled-evolution
  checks. Runtime QA artifact `9941635878` has digest
  `sha256:2f4e0cf5c1124d31d8f845b318b8bf637dee48df9946631bddb13a75c3a86642`;
  Universal artifact `9941733901` has digest
  `sha256:729dbdd8dc2059c64204fec30619422116ce53079aad8f2175e68260a1f8887f`.
  This closes the deterministic local release-file/event crash boundary only. It is not
  authorized test-channel publication, remote reconciliation, signing, notarization or
  SOP-10 completion.
- Product commit `d6a4fb27ad719b378961b740aa348831e8d6cffb`, GitHub CI run
  `33886038527`: release-package recovery now rejects symbolic links and non-regular
  paths before reading JSON or restoring an audit event. The regression fixture moved
  the exact valid package bytes outside the managed run directory, replaced the expected
  path with a link, and proved the matching request still fails closed without creating
  `release_package_created`; restoring the same bytes as a local regular file then
  recovered normally and remained idempotent. All 278 Runtime tests and the Runtime,
  Apple Silicon, Intel and Universal jobs passed, including bundled-Runtime smoke,
  project isolation, staged update, populated rollback and controlled-evolution checks.
  Runtime QA artifact `9941990035` has digest
  `sha256:1d6474f5e56f9f11eaa66ed2127e88bdec3b6023bb3db0339b2679372f9e5809`;
  Universal artifact `9942199014` has digest
  `sha256:607e363c7fbccb32401ab025bde2018f82d41af873b7943cd157384a6339d174`.
  This closes the managed release-package path-containment checkpoint only, not real
  platform publication/reconciliation, human acceptance, signing, notarization or
  SOP-10.
- Product commit `a003451089cec816d60823eaece7d124368aeaf2`, GitHub CI run
  `33887300646`: stored release packages and publication dry-runs now require their
  project and episode identities to match the owning production run after their canonical
  self-digests are recomputed. Regression fixtures changed a package to another project
  and a dry-run to another episode, recomputed each otherwise-valid SHA-256, and proved
  both exact replay paths fail closed without adding an event; restoring the original
  durable bytes retained normal recovery. All 278 Runtime tests and the Runtime, Apple
  Silicon, Intel and Universal jobs passed, including bundled-Runtime smoke, project
  isolation, staged update, populated rollback and controlled-evolution checks. Runtime
  QA artifact `9942508207` has digest
  `sha256:d52d2d8da46932c6678e7c1317f9c6cd065e6ef8491d69f9a4c7d301abe33a49`;
  Universal artifact `9942618267` has digest
  `sha256:fd017b67088694b74fb3667096b8c4dd83137fc755348b5477cbc0322ec1a357`.
  This closes cross-entity release-artifact replay only, not derived-content revalidation,
  authorized publication, human acceptance, signing, notarization or SOP-10.
- Product commit `1fbee021dd3849e66649d4783f28017b6ae51a68`, GitHub CI run
  `33888340689`: stored release packages now independently regenerate their expected
  artifact inventory from the current output seal, reload all five release-blocking QA
  reports and require their current PASS digests, while stored publication dry-runs
  independently recompute the approval/platform binding, creation time, duplicate guard,
  adapter version and compiled adapter plan. Regression fixtures rewrote each artifact
  into a different but internally self-consistent JSON document and recomputed its outer
  digest; altered sealed artifacts, QA bindings, duplicate guards, adapter versions and
  upload-capable compiled plans were all rejected before replay or reconciliation. All
  278 Runtime tests and the Runtime, Apple Silicon, Intel and Universal jobs passed,
  including bundled-Runtime smoke, project isolation, staged update, populated rollback
  and controlled-evolution checks. Runtime QA artifact `9942921540` has digest
  `sha256:dbb10757485c0b225eb487282dcdc13ff683eebf1f695857d7e46e5097d4c8ec`;
  Universal artifact `9943088344` has digest
  `sha256:379e8ec53c061a8eb1909662ea562f9a24824de56be5c31502b226b1de0cb91a`.
  No provider, paid or publication network operation occurred. This closes derived-content
  revalidation for local release artifacts only, not authorized test-channel publication,
  remote reconciliation, human acceptance, signing, notarization or SOP-10.
- Product commit `33b464c0bbbe00242b75432f2514e173ba1616d5`, GitHub CI run
  `33889884604`: publication reconciliation reads now bind the validated record to its
  current production run, project and episode plus the SQLite row's platform, remote
  identity, request and idempotency digests. Active records additionally reload and
  revalidate the current release package and publication dry-run before read-only metrics
  learning can consume them. Negative database fixtures changed the project identity,
  row remote identity and release manifest while recomputing the record digest; each was
  rejected before verifier access or metric creation. Imported backup records without
  restored local media remain available as historical read-only evidence, but cannot
  initiate new metrics synchronization until their trusted local release inputs exist.
  All 278 Runtime tests and the Runtime, Apple Silicon, Intel and Universal jobs passed,
  including bundled-Runtime smoke, project isolation, staged update, populated rollback
  and controlled-evolution checks. Runtime QA artifact `9943471052` has digest
  `sha256:6ac864d7badf471a0e48d92d7da88feb022f8d6fa5495610b6163febcbdbfc1e`;
  Universal artifact `9943649673` has digest
  `sha256:4f109d0f2f1b90a3ac7183d063a95cf028a63343097407bb741ef70fa2e0fff6`.
  No provider lookup, paid call or publication write occurred. This closes the local
  reconciliation cross-entity binding checkpoint only, not authorized remote identity
  reconciliation, human acceptance, signing, notarization or SOP-10.
- Product commit `3cb1e7bf8464f4cb808f30bd0f105c92fa1d7304`, GitHub CI run
  `33891140774`: stored publication metric snapshots now bind every identity and request
  field to their SQLite row, owning run hierarchy and validated publication record;
  stored director strategies bind their row identity and immutable revision to an episode
  in the owning project and to the exact current metrics digest. Negative fixtures rewrote
  the metric project or publication record and the strategy target episode or source
  metrics digest, recomputed each outer record digest, and proved reads and replay fail
  closed. The isolated native learning fixture now includes its own internally bound,
  local-only reconciliation evidence, so packaged UI QA exercises the same graph without
  contacting a provider or claiming a real publication. All 278 Runtime tests and the
  Runtime, Apple Silicon, Intel and Universal jobs passed, including bundled-Runtime
  smoke, project isolation, staged update, populated rollback and controlled-evolution
  checks. Runtime QA artifact `9943993275` has digest
  `sha256:02c2f4b4985824f0bc135ce32be5cfbd6ce2eed2ed06eea1253a28a4a28a35c0`;
  Universal artifact `9944142005` has digest
  `sha256:cc8400cd8c1a6440a7d5cc5fd317e8f444bea1502ff58ecbeeb1bffb94594202`.
  No provider lookup, paid call, production or publication write occurred. This closes
  deterministic local learning-record graph integrity only, not authorized platform
  observation, human learning-loop acceptance, signing, notarization or SOP-10.
- Product commit `bd2cb87868dfa0489da22e246f0fe16d9c78fac5`, GitHub CI run
  `33892239160`: after read-only metric verification and local strategy preflight, the
  Runtime now acquires the SQLite write lock and re-reads the completed run hierarchy,
  published source episode, immutable publication identity, next episode selection and
  target editability before inserting either the metric snapshot or director strategy.
  A deterministic race fixture moved the selected next episode into preproduction after
  preflight but before the transaction; the request failed closed and both learning tables
  retained zero rows, after which an unchanged retry succeeded normally. All 278 Runtime
  tests and the Runtime, Apple Silicon, Intel and Universal jobs passed, including
  bundled-Runtime smoke, project isolation, staged update, populated rollback and
  controlled-evolution checks. Runtime QA artifact `9944403931` has digest
  `sha256:126c3403d706f0a8baa337a532bf0cdd7edb26898bc3a386d3b22374758abd35`;
  Universal artifact `9944542694` has digest
  `sha256:6ff555ae6d38d4c4df023b6f5679438a48b8a9a91eb783eb184d33145a8ba1b4`.
  No provider lookup outside deterministic fixtures, paid call, production or publication
  write occurred. This closes the local learning transaction authority checkpoint only,
  not authorized platform observation, human acceptance, signing, notarization or SOP-10.
- Product commit `dd23494d56ad488d22dbc7f46882fabf1e7f0434`, GitHub CI run
  `33893233651`: publication reconciliation now acquires the SQLite write lock after
  independent identity lookup and re-reads the completed run, project/season/episode
  hierarchy, release-ready episode state and absence of any competing run/platform,
  idempotency-key or remote-publication identity before inserting the immutable record
  and lifecycle event. A deterministic verifier race changed the episode to blocked while
  lookup was in flight; the final transaction rejected stale authority with zero
  reconciliation rows and no `publication_reconciled` event, after which restoring the
  release-ready state allowed a normal request. All 278 Runtime tests and the Runtime,
  Apple Silicon, Intel and Universal jobs passed, including bundled-Runtime smoke,
  project isolation, staged update, populated rollback and controlled-evolution checks.
  Runtime QA artifact `9944782929` has digest
  `sha256:46a7d246769a426ad9586f2f731cd3b320d314157685960b00e85797eb427e93`;
  Universal artifact `9945019952` has digest
  `sha256:f0c3f3036aafea21dbd702044c2fdeaafae6253463c9817acaec3a727d67682d`.
  Only deterministic local verifier evidence was used; no paid call or publication write
  occurred. This closes local reconciliation transaction authority only, not authorized
  platform reconciliation, human acceptance, signing, notarization or SOP-10.

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
- Commits `da9a6d0`, `aed2375` and `bc1f844`, GitHub CI run `33439917162`: an
  offline fail-closed rehearsal now creates a ten-episode older-adult project, approves
  every episode script, exports an immutable backup, restarts the exact Runtime over the
  same local SQLite/data roots and restores the backup into clean roots. Source, arm64,
  x86_64 and universal executions all preserved episode numbers 1–10, all ten
  `script_approved` states, schema v14 and the backup payload hash. Their persistent JSON
  report SHA-256 values are respectively `f6770d85309dc1f6a57ada91ab1cff1c1002056020f55d8f22e4bc629ededd9b`,
  `9437c3353afbe1e844ec1936fe6cd78eb09e2b1d441b325a80591750191fa4b6`,
  `9660a11e4fc4c3a877d6f6d75aab49a7af804bbacf87da31f0b779ef2d806c2c`
  and `4a0647c0669b2fdae488e964d71efeaab298de296ad71f16774429907b94090b`.
  The universal artifact is `9776013167`, GitHub artifact digest
  `sha256:ef9e590835d963cd56209379c0b54d372942d7662ab43c3103231020960dbf1e`
  and downloaded ZIP SHA-256
  `cd0b2e0c0a4e641aa2565f448490cfd2e2fc89c547548d7a6d82e10cc8fe65d5`.
  Its native app, Runtime and visual analyzer all contain both arm64 and x86_64 slices.
  The downloaded candidate passed the same rehearsal again on a local Apple Silicon Mac;
  local report SHA-256 is
  `9e4c9385f15d4a841d61761c055cca4c191363ea7321a451e128017f7f02a0a9`.
  The first evidence-persistence attempt correctly failed universal merge because its
  artifact root changed; `bc1f844` preserves the prior artifact layout while retaining
  downloadable QA JSON. No step downloaded an update, contacted a model/provider or
  performed a paid/publication action. This closes only the local data restart and clean-
  backup rollback checkpoint; it is not an old-version-to-new-version installation test.
- Commits `6dae281` and `7d1b53d`, GitHub CI run `33469370874`: the packaged app now
  contains a universal native update helper, disabled-by-default trust policy, exact
  Ed25519 manifest/package verification, monotonic build and expiry enforcement, bundle
  identity/version/signature checks, persistent idempotent transaction phases, health-
  confirmation commit, crash/timeout rollback and protected local-data hashing. Swift
  unit tests cover signature validity, tampering, wrong channel, replay/downgrade, expiry,
  package mutation, crash recovery, idempotency conflicts and data mutation. The exact
  arm64, x86_64 and merged universal bundles then passed offline packaged-helper QA from
  `0.1.0 (1)` to `0.1.1 (2)`: a tampered manifest and replay were rejected, an
  unconfirmed candidate rolled back, a confirmed candidate committed and the ten-episode
  data fixture remained unchanged. Staged-update report SHA-256 values are respectively
  `474ed028feaf7f7ab027de8eb6acdb032bab669526b27bc909764c6aa3b4be01`,
  `a31935e9daf61cdab8e113188b70cf0197be6f35f57e8ceda3a93c75e12fbf9b`
  and `f3a68ecfc1ca61b5b56053a7098c038cb970d641d303d0340f3d8895f237db12`.
  Universal artifact `9786074323` has GitHub digest
  `sha256:a8880a3491170631bd828e34200492c91fc21eb7e574c2cefa8b1c97b15c76f4`;
  its downloaded ZIP SHA-256 is
  `961aac263ff217500371f8a1ec6598f70e2d3a65e32c8eb3fde80055b6239765`.
  Its native client, Runtime, visual analyzer and update helper all contain arm64 and
  x86_64 slices and the deep signature structure verifies. This was offline with an
  ephemeral QA key and ad-hoc app signatures; no update was downloaded or published.
- Commits `d9e0e16`, `c84c32e` and `e8be5e3`, GitHub CI run `33471853902`: update
  discovery is now a separate disabled-by-default boundary with an exact HTTPS-origin
  allowlist, redirect rejection, 64-KiB manifest and 2-GiB package limits, atomic partial
  downloads, content-addressed package paths, signed-manifest-first verification and a
  persistent idempotency record binding installed build plus complete discovery/trust
  policy. All 45 XCTest cases plus the Swift Testing discovery/fetcher suites passed on
  Apple Silicon and Intel; snake_case packaged trust and discovery policies have explicit
  decoding regression tests. Runtime, architecture builds, bundle verification/smoke,
  staged update, populated ten-episode restart/rollback and universal merge all passed.
  Universal artifact `9786896858` has GitHub digest
  `sha256:db223f3e44f7864d3db927057fb20370b3213217e26b95b997056ad86a29aa79`;
  its downloaded inner ZIP SHA-256 is
  `acaf18d528308e6228dbf20293f82cc7fda18f21806f1b53e73eb2382f54a68c`.
  Independent inspection found both `x86_64` and `arm64` update-helper slices, decoded the
  exact packaged policies and observed exit 1 with
  `nalu-update-helper: Update discovery is disabled.` The universal staged-update and
  rollback evidence-file SHA-256 values are respectively
  `7052afb140caf7e7371daa842a4f075f3a26a5f8196456c65886c52165316f01` and
  `dd0e3abb68ae8e574af57d1a8d3190b32577fc599c322afdb577bbea5e2d255c`.
  This proves only the offline/local-fixture boundary; no production origin was contacted.
- Commit `9981d8e` makes every Runtime database connection a closing context manager,
  refuses reuse of an unmanaged loopback listener and synchronously terminates the owned
  Runtime process tree. Commits `4864976`, `8433ded` and `f2dfd40` extend the ownership
  boundary through every native request and give startup denial an unambiguous red
  disconnected state. CI run `33821294202` passed all Runtime, Swift, arm64, x86_64,
  Universal, packaged smoke, staged-update and populated-rollback jobs on exact product
  commit `f2dfd40060e1bda300cd6f580f85b8d489d2f5ff`.
- Fresh native QA used that run's exact Universal artifact `9918470084` (GitHub digest
  `sha256:124d1450cbaf911ccbb727bbc0b400fcbb5477bbcd7f25172cea0dc0a32ad401`,
  inner ZIP SHA-256
  `27103d7ffcbf123ce6528d130693321dc9d3ca247c6ae5fa4d1230ff844f0718`).
  The owning app loaded only its temporary SQLite fixture. During 1,200 successful
  database-backed project-list requests, 285 concurrent descriptor samples observed at
  most one transient fixture SQLite descriptor, zero descriptors beneath the user's
  normal Application Support database, and zero fixture/user descriptors after the
  requests. A simultaneous denied process spawned no child Runtime, sent no project
  request and displayed no owner data. A normal application Quit then removed the native
  app, PyInstaller wrapper, Runtime child and TCP listener on port 8765 in 1,493 ms.
  These close the packaged ownership/descriptor/quit regression checkpoint only; the
  artifact remains ad-hoc signed and is not clean-install, Developer ID, hardened-runtime
  or notarization acceptance.
- Commit `b36d06dcbd3d00322623b09edd9e9da3e1bf73b2` adds an independent
  fail-closed verifier for both packaged staged-update and populated rollback reports.
  It requires the exact schemas and fields, recomputes both canonical report digests,
  enforces a one-build monotonic transition, rejects failed tamper/replay/rollback/data-
  preservation claims, requires ten consecutively numbered approved episodes across the
  same Runtime schema, and prevents either report or the release ZIP from being
  substituted beneath a trusted artifact digest. The Universal job now executes this
  verifier before upload and publishes its canonical receipt. Negative fixtures cover
  non-monotonic builds, failed protected-data preservation, digest changes, truncated
  episode state, signed-update overclaims and artifact report substitution. GitHub CI
  run `33848292912` passed 219 Runtime tests, lint and contract audits, real HTTP and
  offline E2E rehearsals, both architecture builds and the Universal build, including
  packaged smoke, staged update, populated rollback and both provenance verifiers.
- The exact Universal artifact `9927490319` has GitHub digest
  `sha256:61cfcd6dac126135f3f593b1eed7c134f245e8454867932f5b70f78c6ecbcbc4`.
  A fresh repository-external download reproduced that outer digest and bound both
  reports plus the application ZIP to the archive byte-for-byte. The inner ZIP SHA-256
  is `e73bd6d9e300ad80a2e86475b68a9a19ede27158eae1f27597fd7a5a17c27345`.
  Staged-update report file/canonical SHA-256 values are respectively
  `07526f8b9da1abde4a7df01c689def2805998153eb1ab433fb59f85943806c8a`
  and `2c3eb566e2e079f9c8e90331e3bf50b67f398af1294d4af1ee5adf9451a9df4d`;
  rollback report values are
  `5aacb74a403a2ac926101b26b1977da09aae3b3503f69848ebb055dd779ccb19`
  and `05f736c4b9f8753e53bf45021cc740164d16349c53f0948e5597ad80660720e1`.
  The independent bound receipt file has SHA-256
  `a4f411cfb31b9c8923efde8352ca703beab173d8ad6e5769e2a0be4fd198a437`
  and canonical digest
  `cf6e1c561a0fb6a2747b2a61c83342943958f04a64d84cc4fdbd7cfee04310b2`.
  It truthfully limits scope to an ephemeral offline/loopback rehearsal: no production
  update was downloaded or installed and no Developer ID, notarization or clean-Mac
  old-version upgrade acceptance is claimed. SOP-11 remains `IN_PROGRESS`.
- Still required before `PASS`: Developer ID signing, hardened runtime, notarized
  universal release evidence, an authorized real update origin and production public key,
  authorized production discovery/download QA, and clean-Mac old-version-to-new-version
  upgrade/rollback QA with populated multi-episode data. The green universal build is
  still ad-hoc signed.

## SOP-12 · End-to-end release-candidate acceptance — IN_PROGRESS

Acceptance scenarios:

1. Older adult creates a personal autobiography using voice and personal photos.
2. Guardian and child create a fictional multi-episode story.
3. A 10-episode project preserves identity, voice and narrative state across episodes.
4. One episode fails generation, survives restart, resumes safely and passes QA.
5. A completed episode creates an offline release package, while paid submission and
   platform publication remain blocked without their separate authorizations.
6. Animation intent selects a capability-checked route; commercial intent with no
   approved adapter remains a useful project but cannot start production.
7. A spoken usability report is redacted, kept local by default and cannot change or
   release application code without the controlled review pipeline.

Completion evidence:

- All scenarios run from a clean signed installation.
- Costs, task IDs, receipts, QA reports and published IDs reconcile.
- No P0/P1 defects remain open.
- SOP-00 through SOP-11 and SOP-13 are revalidated on the same release commit.

Current evidence:

- Implementation of the offline, non-claiming scenario rehearsal has started. This status
  change is not E2E acceptance: no scenario may become `PASS` until it runs from the same
  signed/notarized installation with reconciled real provider and publication evidence.
- Commit `205f07b` adds a machine-readable offline rehearsal for all seven scenario
  structures. It runs 19 selected integration and negative tests with credential-like
  environment variables removed, paid submission and publication disabled, and a pytest
  socket guard that rejects every non-loopback connection. Each scenario records its
  remaining real evidence and is labeled only `STRUCTURE_REHEARSED`; the report keeps
  paid calls, publication, external writes, signed/notarized installation, provider and
  publication reconciliation, human acceptance and `project_complete` literal false.
  GitHub CI run `33509959816` passed the 131-test Runtime suite, the separate rehearsal,
  real HTTP smoke, Swift tests, independent arm64/x86_64 builds and smokes, staged update,
  populated rollback and universal merge (jobs `99863051984`, `99863052081`,
  `99863051775`, `99864552433`). Runtime evidence artifact `9801262791` has GitHub digest
  `de0fbd8d3be1630e0cbe2f3f7b6c66a9979f9c466fc08520bdddb6defa2e725e`; the downloaded
  rehearsal JSON SHA-256 is
  `c9f1b8e6c18011f44c21301a57040624bb8004704dc2ffe75cf833a29628e2b2` and its canonical
  evidence digest is `9ecfce0bd1c72a278589f55fdebeabd10e1d74875d3f06861062eb58a6f35fd2`.
  Universal artifact `9801431356` has GitHub digest
  `3093b4c912f445648838626a6b2afb68fa06000a13a2599b01bbcd521f6fbf1d`.
  This closes only the offline structural-rehearsal checkpoint; SOP-12 remains
  `IN_PROGRESS` until all scenarios run from one signed/notarized candidate with real
  authorized costs, task/receipt/publication reconciliation and human acceptance.
- Commit `6334da1`, GitHub CI run `33511396984`: a separate
  `nalu.release-acceptance/v1` manifest and CI audit now reject whole-product completion
  unless all eight release gates are `PASS` and every evidence record binds the same
  40-character source commit and universal artifact SHA-256. False completion before all
  fourteen SOP items pass, cross-commit evidence, cross-artifact evidence and `PASS`
  evidence smuggled into a `NOT_READY` manifest fail automated negative tests. The
  repository manifest deliberately remains `NOT_READY` with
  `completion_eligible: false`. All 136 Runtime tests, real HTTP smoke, offline seven-
  scenario rehearsal, arm64/x86_64 builds, packaged smokes, staged update, populated
  rollback and universal merge passed. Runtime QA artifact `9801839813` has GitHub digest
  `sha256:cc0ec37f92a0172fc2973e76057b963f9fb2da76f27968fc00478e9ffea76d3d`;
  universal artifact `9802090651` has GitHub digest
  `sha256:70670bc3a08be82cccf14d205b1dae1febc4104a15cb6becb3a32614942ac619`.
  This is an anti-false-completion checkpoint, not signed/notarized or real E2E evidence,
  so SOP-12 remains `IN_PROGRESS`.
- Commit `1c2fe5b`, GitHub CI run `33512639151`: release evidence is now validated by
  gate type, not merely by a shared URL and digest. Developer ID evidence must include
  team, notarization, hardened-runtime, staple and Gatekeeper facts; provider evidence
  must reconcile real task IDs, receipt digests, exact currency/cost and zero ambiguous
  transactions; publication evidence must reconcile real IDs and receipts; human QA must
  include VoiceOver, Accessibility Inspector, older-adult and guardian/child sessions;
  all seven exact SOP-12 scenarios must individually be `PASS`; clean install, populated
  ten-episode upgrade/rollback, zero P0/P1 and all fourteen same-candidate SOP states are
  separately required. Automated negatives reject a missing provider receipt and reject
  `STRUCTURE_REHEARSED` as a scenario result, while a complete synthetic contract fixture
  proves the schema can reach `completion_eligible: true` only when every required field
  is present. All 138 Runtime tests, real HTTP smoke, offline rehearsal, architecture
  builds/smokes, staged update, populated rollback and universal merge passed. Runtime QA
  artifact `9802348871` has GitHub digest
  `sha256:a571bb23e8450980f46a9ddc503cd4ff24bed98f29215f91a9694191341e278f`;
  universal artifact `9802512109` has GitHub digest
  `sha256:97999fc6d68109b9c8610afe434177c254bd8af66332f443eb0d1f0fadcadd4e`.
  The repository manifest still truthfully reports `NOT_READY`; no real receipt, signed
  installation, human review or publication is claimed, so SOP-12 remains `IN_PROGRESS`.
- Commit `947bba252fa0e9b06253176a7f972ac29e267994` adds an independent
  verifier for the seven-scenario offline rehearsal instead of trusting its generator or
  CI log. It requires all seven ordered scenario identities, their explicit remaining
  real evidence, `STRUCTURE_REHEARSED` rather than release acceptance, the exact unique
  test count, all no-paid/no-publication/no-external-write/no-signing/no-human-acceptance
  flags, non-loopback blocking and literal `project_complete: false`. It recomputes the
  canonical report digest and every declared source-file SHA-256 directly from the exact
  Git commit, then can bind the report bytes to the downloaded GitHub artifact digest.
  False completion, false scenario acceptance, canonical tampering and report
  substitution are permanent negative tests. GitHub CI run `33849341891` passed 224
  Runtime tests, lint and contract audits, the 21 selected scenario tests and verifier,
  real HTTP smoke, both architecture builds and Universal packaging with all packaged
  evidence gates.
- Runtime QA artifact `9927797876` has GitHub digest
  `sha256:4d8f6ab99390c4ddfcf256e13dbcc928efb0608c6d5bf3e255c80872fb29dc7a`.
  A fresh repository-external download reproduced that digest, matched all ten declared
  source blobs against commit `947bba252fa0e9b06253176a7f972ac29e267994`, and
  bound the exact report to the archive. Report file and canonical SHA-256 values are
  `8b9571d89900bb574d0bea811ab915750894bca4bfbb6d5192d62c3e95c3cd98`
  and `69ebff7a6b4c50faa7b7420abcc3c39f5eb5d9abf18181d875b283e450ffda31`.
  The independently bound receipt file has SHA-256
  `5706c74e432b21dcd3d162ca68d645cd7c92fb0e5f0004ffa7cf24eda3a97f12`
  and canonical digest
  `4b87f7e40cfda36182662c610f558900db987723e1178e68f43ebfc576202f35`.
  Universal artifact `9927874653` from the same run has GitHub digest
  `sha256:ad1d03a2988060d29ca8ae4ddaf2b0cdbcfe1ce3c511f2b2db695e39bc0e379f`.
  This closes only offline structural evidence provenance. All seven scenarios still need
  the separately listed signed/notarized, authorized provider/publication and human QA
  evidence on one candidate, so SOP-12 remains `IN_PROGRESS`.

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
- Commits `6dae281` and `7d1b53d`, GitHub CI run `33469370874`: the release side now has
  the offline, fail-closed Ed25519 verification and health-gated rollback primitive needed
  by the governed pipeline. It deliberately has no feedback-to-change linkage and cannot
  mark a report released merely because an unrelated valid package was installed.
- Commit `fd6633c`, GitHub CI run `33473090642`: schema migration 15 and project-export
  v10 add one immutable local `qa_evidence_linked` record joining the exact review-bundle
  digest to a reviewed 40-character commit, the matching successful CI head and artifact,
  an installed Developer ID/notarization/Gatekeeper receipt and an older-build rollback
  rehearsal that preserved project data. It rejects missing or changed idempotency keys,
  digest/commit/artifact mismatches, unverified signing facts, non-older rollback builds,
  recomputed export tampering and changed replays. The raw idempotency key is not stored.
  The record performs no network call, leaves feedback at `ready_for_review` and has a
  literal `release_claimed: false`; locally supplied receipts therefore cannot claim an
  actual rollout. All 95 Runtime tests, OpenAPI compatibility, real HTTP smoke, arm64 and
  x86_64 Swift/build/bundle smoke, staged update, populated ten-episode restart/rollback
  and universal merge passed. Universal artifact `9787326974` has GitHub digest
  `sha256:92f18541e8d407e8ba6da133d09d8622bbb8c1d1753f10e074b96e1a7cdfed03`;
  its downloaded inner ZIP SHA-256 is
  `385b8853462f0bd65624acbd412c32b98576c101b0d140456a71ab611c226d5e`.
  Independent inspection confirmed a universal Runtime and schema-15 staged/rollback
  reports with evidence-file SHA-256 values
  `5f1907d73a9f00bdefe4948f1427ad1a153ef53f0066d2d599bb2a7615b17ca3` and
  `46381bdd3fa0fc785c3a9e7ee245ad82e15cc3aec5a86398bb55b7993d228dc2`.
- Commit `0d651cb`, GitHub CI run `33474338480`: schema migration 16 and project-export
  v11 add one immutable human-confirmed local triage record per authorized review bundle.
  It binds the exact bundle digest, priority, disposition, optional same-project duplicate,
  rationale and reviewer; secrets are redacted and confirmation/idempotency values are
  retained only as hashes. Missing confirmation, local-only input, cross-project/self
  duplicates, changed replay and recomputed backup tampering all fail closed. Prompt-
  injection text remains inert while `tool_calls` is empty and `code_change_performed` and
  `network_call_performed` are literal false; feedback remains `ready_for_review`. All 96
  Runtime tests, OpenAPI compatibility, real HTTP smoke, both architecture builds/smokes,
  staged update, populated ten-episode restart/rollback and universal merge passed.
  Universal artifact `9787709313` has GitHub digest
  `sha256:7b8dfa2457dfd95aaf1245ef4ca55916cec0882c42ff7105307970f8cc83a13c`;
  its downloaded inner ZIP SHA-256 is
  `0283fa52292d3387f9ed66d886fe0d9ab5e2d540922b0d43be8c8aed17a7d7fe`.
  Independent inspection confirmed a universal Runtime and schema-16 staged/rollback
  evidence-file SHA-256 values
  `a0367c122e5138186e5b96914206885bf194e859eabb90ad06644eab10701028` and
  `d6414b8d7c56084456d30af0474a7c266ef40fe4eef164ca27ed74cbc3ba4c21`.
- Commit `e0bbcd7`, GitHub CI run `33475858943`: schema migration 17 and project-export
  v12 add a persistent, idempotent issue-export transaction boundary after authorized
  bundle review and human triage. The distributed administrator policy is disabled and
  target-free, and the distributed transport denies I/O. An injected local fixture proves
  the bounded redacted payload has no attachments, persists before I/O, stores only the
  idempotency-key hash, replays a confirmed result without another call, rejects changed
  inputs and quarantines an uncertain outcome without automatic retry. Concurrent requests
  make at most one transport call; policy/endpoint/repository traversal, receipt and
  backup/restore tampering fail closed. No external service was contacted. All 104 Runtime
  tests, OpenAPI compatibility, real HTTP smoke, Swift tests, both architecture builds and
  bundled smokes, staged update, ten-episode schema-17 restart/rollback and universal merge
  passed. Release verification now rejects a packaged feedback-export policy unless it is
  disabled, unauthorized and target-free. Universal artifact `9788268553` has GitHub
  digest `sha256:6e008093793611ea6e26fee97d65881c5ce202781f3962e2351b047c2abf00c8`;
  its downloaded inner ZIP SHA-256 is
  `1b1769f8b24d9b8e8ecb7337a823c3dce920e648abe4748740469f5184f0f47e`.
  Independent archive inspection found the disabled packaged policy at SHA-256
  `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `421459959ce53f1ce2df6a795640ade85377c0cd88abce237115750615610b95` and
  `38a26a564440fa731addbff275d18ad8b2780d0a43aac551ce755a2efd54235d`.
- Commit `837a1dc`, GitHub CI run `33477408218`: schema migration 18 and project-export
  v13 add immutable administrator reconciliation for export transactions left in
  `submitting` or `ambiguous`. It requires the original idempotency key, exact policy and
  payload digest plus explicit confirmation, then invokes a separate read-only verifier;
  it never calls issue creation again. A verified receipt atomically confirms the stored
  export, while verified absence atomically rejects it. Both records state that creation
  was not retried and reconciliation performed no external write. Wrong keys, digests or
  confirmations fail before verification; exact replay does not re-query, conflicting
  replay, malformed results and recomputed backup tampering fail closed. Provider response
  bodies and verification evidence are reduced to bounded, non-secret digests/receipts.
  The distributed verifier denies every call; found/absent tests used injected local
  fixtures and contacted no external service. All 105 Runtime tests, OpenAPI compatibility,
  real HTTP smoke, Swift tests, both architecture builds/smokes, staged update,
  ten-episode schema-18 restart/rollback and universal merge passed. Universal artifact
  `9788809600` has GitHub digest
  `sha256:ecf6a3096ce4f2d9f25da1741f4dcb6ced151ee8cf1105c52b590d3ae9444807`;
  its downloaded inner ZIP SHA-256 is
  `81b8dcea473c511c285d45d661d93c09038319871d5e50b39d7f6eb5346d1520`.
  Independent inspection reconfirmed the disabled packaged policy at SHA-256
  `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `f37511b3721dee767ed72e1a3dac7e7af5b565b94f894863abbad410d8f7c365` and
  `554d7c48bb1579c48ba99c11fb2fe277f312c0f448500fe867baf98644dfc05b`.
- Commit `6442f60`, GitHub CI run `33478553480`: schema migration 19 and project-export
  v14 add an immutable, explicitly confirmed local development work order after an
  accepted human triage and a confirmed issue-export receipt. The record binds the exact
  triage/export digests and remote issue identity to a scoped title, implementation scope,
  acceptance tests and privacy/accessibility requirements. Report text remains inert;
  `tool_calls` is empty and branch creation, code change, merge, signing, release and
  network-call flags are literal false. Missing or changed confirmation/idempotency,
  cross-project or unconfirmed inputs, secret-bearing content, conflicting replay and
  recomputed backup tampering fail closed. This checkpoint creates no branch, invokes no
  development agent and makes no external call. All 105 Runtime tests, OpenAPI
  compatibility, real HTTP smoke, Swift tests, both architecture builds/smokes, staged
  update, ten-episode schema-19 restart/rollback and universal merge passed. Universal
  artifact `9789180440` has GitHub digest
  `sha256:68397199c7eba6f6b30638457563ee901868857555dac7d47f5b3dd751b5682b`;
  its downloaded inner ZIP SHA-256 is
  `46c0e70388a852d2d783c3c32dc684792514187d859f05703e9e62182d9cb14c`.
  Independent inspection reconfirmed the disabled, unauthorized and target-free packaged
  feedback-export policy at SHA-256
  `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `174a03a11adcd6667f436ec1466be0181b29bddc4f05933efc2004f6e33bcbee` and
  `f15ec1320dc19dca999c41e4922bc54b433846eda1b867a15b898222e319fca5`.
- Commit `54c2a23`, GitHub CI run `33480223053`: schema migration 20 and project-export
  v15 add a separate persistent development-handoff transaction after an approved work
  order. The packaged policy is disabled, unauthorized and target-free, and the
  distributed transport denies I/O. An injected local fixture proves explicit
  confirmation, stable idempotency, pre-I/O `submitting` persistence, bounded attachment-
  free input, exact confirmed replay without a second call and `ambiguous` quarantine
  without automatic retry. The payload and receipt can claim only handoff acceptance:
  report text remains inert and branch, code, merge, signing and release flags stay false.
  Changed inputs, credential-bearing/invalid endpoints or receipts, malicious policy,
  payload/backup tampering and retry after an uncertain result fail closed. No real
  development agent or external service was contacted. All 111 Runtime tests, OpenAPI
  compatibility, real HTTP smoke, Swift tests, both architecture builds/smokes, staged
  update, ten-episode schema-20 restart/rollback and universal merge passed. Universal
  artifact `9789789616` has GitHub digest
  `sha256:49cbd731c67adbac1d8df154b80f1fe7eabd856b9904431a9e411f9ea8b79a42`;
  its downloaded inner ZIP SHA-256 is
  `e1aa8d5917f7a61dde73112ef66830b81758b751de44c5c0c99203545b590840`.
  Independent inspection found the disabled packaged handoff policy at SHA-256
  `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`
  and reconfirmed the disabled issue-export policy at SHA-256
  `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `f7094df64c948e9c9e923f6b37cbb4e2a413e9653bbe0986030fd1b61d960a2b` and
  `fd58b8b7eebb0df3f09fff185bdfb56ef09371f9f55e7963f8e4ab08c2fb3c03`.
- Commit `9aa4790`, GitHub CI run `33481481743`: schema migration 21 and project-export
  v16 add immutable read-only reconciliation for development handoffs left `submitting`
  or `ambiguous`. It requires the original idempotency key, exact payload digest, same
  authorized policy and explicit administrator confirmation, and it never invokes work-
  order submission. An injected verifier can independently return a bounded accepted-task
  receipt or prove absence; Nalu atomically confirms or rejects the transaction. Exact
  replay does not query again, while changed keys/digests/confirmation, malformed or
  contradictory lookup results and recomputed backup tampering fail closed. The record
  states `work_order_submission_retried: false` and `external_write_performed: false`.
  The packaged verifier denies all calls; found/absent QA used local fixtures and contacted
  no external system. All 111 Runtime tests, OpenAPI compatibility, real HTTP smoke, Swift
  tests, both architecture builds/smokes, staged update, ten-episode schema-21 restart/
  rollback and universal merge passed. Universal artifact `9790251615` has GitHub digest
  `sha256:4714589ea0e5b32946b5512baa23855642c96ae10c46ead74576dc0a6b921318`;
  its downloaded inner ZIP SHA-256 is
  `fe02a0d78cc60bfc35bba8d089154652768665d80725e81c2b16f18938680f71`.
  Independent inspection reconfirmed the disabled handoff and issue-export policies at
  SHA-256 `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`
  and `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `8bcb82c5214856616bd8a11566db5346df3a56aa98934ee9029752b927c6ab0b` and
  `3f13b0ca7c1d6ba8a548d92c770c053678455815d0acf25d0f49e0cff94596ee`.
- Commit `5b0cf95`, GitHub CI run `33483163186`: schema migration 22 and project-export
  v17 add one immutable development-result record after a confirmed handoff. A separately
  injected read-only verifier must bind the exact handoff to the approved GitHub
  repository, a bounded branch, exact pull request, 40-character commit and test-evidence
  digest after explicit confirmation and a stable idempotency key. Raw verifier evidence
  is reduced to a digest; exact replay does not query again. Missing/changed confirmation,
  key or handoff digest, unsafe repository/branch/review data, malformed results and
  recomputed backup tampering fail closed. Literal safety fields prove this operation did
  not check out a repository, execute report text or code, invoke tools, merge, sign,
  release or write externally. The packaged verifier denies every call; QA used only an
  injected fixture and contacted no real development system. All 111 Runtime tests,
  OpenAPI compatibility, real HTTP smoke, Swift tests, arm64/x86_64 builds and bundle
  smokes, staged update, ten-episode schema-22 restart/rollback and universal merge passed.
  Universal artifact `9790867082` has GitHub digest
  `sha256:b2b1a8ec059de9281ccb3d9d22fbc27211f0578ef46fdf27acd4416f919f6504`;
  its downloaded inner ZIP SHA-256 is
  `3d72a81a4b93dbd7f52612884f0ffd54001023400a47e813da0b860b4588f564`.
  Independent inspection reconfirmed the disabled handoff and issue-export policies at
  SHA-256 `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`
  and `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `c502ca98acbc9e4231cfcc80fa2ba43b69315b34ec72b9693272f65dfc03f251` and
  `19e3de652d0a8d42fcd257d1ddf80550886a81f24d284c99ec0dde36c91ddc38`.
- Commit `8ad807e`, GitHub CI run `33484426958`: project-export v18 now binds every
  new local release-evidence linkage to the immutable verified development-result
  record. Repository, pull-request URL, commit and test-evidence digest must match
  exactly; the linkage request and record hash-bind the development-result digest.
  Import validates both records independently and then cross-validates them, so a
  recomputed backup that substitutes a different review URL is rejected. Backups
  through v17 remain compatible and no SQLite schema migration was required. All 111
  Runtime tests, OpenAPI compatibility, real HTTP smoke, Swift tests, arm64/x86_64
  builds and bundle smokes, staged update, ten-episode schema-22 restart/rollback and
  universal merge passed. Universal artifact `9791377499` has GitHub digest
  `sha256:cb522bbf7aa6c0768ee0a096caa460ab90858b95e612a9bb53d6e2fe67966c12`;
  its downloaded inner ZIP SHA-256 is
  `50dd23aa7a93243592f61a8be211a4494b7da490c7db1a87a77ed04157d63c98`.
  Independent inspection reconfirmed the disabled handoff and issue-export policies at
  SHA-256 `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`
  and `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `7b58b93f477e8684a091f6957be6293e9d56abf48fe283072a78a46abb2d21bc` and
  `da7cf2fb1850b6f289de0b2e31a75607b3c637f86bef28d594e4196a984f5d4a`.
- Commit `5377759`, GitHub CI run `33486106442`: schema migration 23 and
  project-export v19 add immutable independent reconciliation of locally supplied
  release evidence. A separate disabled-by-default verifier must return the identical
  CI run/head/artifact, installed version/build/product commit/provenance, Developer ID
  team, notarization submission, signature/notarization/Gatekeeper results and older-
  build rollback evidence after explicit confirmation and a stable idempotency key.
  Any mismatch fails closed; exact replay does not re-query. Only a digest of bounded
  verifier evidence is retained, while download, installation, signing, notarization,
  release, external-write and release-claim fields remain literal false. Export/import
  verifies the complete linkage and request hash chain and rejects recomputed tampering.
  The packaged verifier denies every call; tests used injected fixtures and contacted no
  real GitHub, Apple or installation service. All 112 Runtime tests, OpenAPI compatibility,
  real HTTP smoke, Swift tests, arm64/x86_64 builds and bundle smokes, staged update,
  ten-episode schema-23 restart/rollback and universal merge passed. Universal artifact
  `9791972981` has GitHub digest
  `sha256:1290b368d9964bea88eeb54691ff8276e14534cfc144016cf48010eeaf6c716c`;
  its downloaded inner ZIP SHA-256 is
  `17c79655ccf3ef84a5da8d1dee9c6d077b8364c662ea08bb1a1f14ccdeb17d8e`.
  Independent inspection reconfirmed the disabled handoff and issue-export policies at
  SHA-256 `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`
  and `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `ba638ad4672a3e8670542fddf3ca3bc488b3e4f890d37f4f30fbcd9b8241e296` and
  `ed9900c7a19ff9a4eec22e13eb9ba667ccd1c791965c01ee85ce2f604efa6454`.
- Commit `2570094`, GitHub CI run `33487099669`: the Runtime now exposes one
  deterministic read-only governed-release readiness report over the complete feedback
  chain. It distinguishes accepted triage and confirmed external/handoff transactions
  from mere row existence, identifies every missing review, development, independent
  CI/Apple/installation and rollback prerequisite, and always keeps staged-rollout
  authorization, real rollout receipt and post-install health as separate gates. Even
  when every pre-rollout check is satisfied, `released` and `release_claimed` remain
  literal false and the report performs no network call or external write. Restored
  projects reproduce the same report. All 112 Runtime tests, OpenAPI compatibility,
  real HTTP smoke, Swift tests, arm64/x86_64 builds and bundle smokes, staged update,
  ten-episode schema-23 restart/rollback and universal merge passed. Universal artifact
  `9792348966` has GitHub digest
  `sha256:accd7aaac3b54e9d03b9bfbf46d55b7c55f13b4c6a0c1e493670b3a9726902d6`;
  its downloaded inner ZIP SHA-256 is
  `33755caec22557ea60aaafcf7a43ae0a8b1a6275aa670b73d1ed56debfd8bcee`.
  Independent inspection reconfirmed the disabled handoff and issue-export policies at
  SHA-256 `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`
  and `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`;
  staged-update and rollback evidence-file SHA-256 values are
  `197172d03fda0c1807dc1003e5c0f6e4b210f1ed7b1441d028bd159213fd0d71` and
  `632a501deaa490e4fc1a0b7e31166d94ab8fe016325f3a1fc1c8626210ca5f32`.
- Commit `c89e53e76b5b9d979264eb2bd9763cc502894b88` turns the current packaged
  controlled-evolution boundary into a release gate and independently verifiable receipt.
  The verifier opens the actual application ZIP, rejects duplicate/missing policy members,
  and requires feedback export and development handoff to remain disabled, unauthorized,
  bounded and target-free. It also proves both packaged policy bytes match their exact
  source-commit blobs, verifies the inner ZIP checksum and can bind that ZIP to GitHub's
  downloaded outer artifact digest. Enabled/targeted policies and release substitution
  are permanent negative fixtures. The receipt explicitly records that automatic code
  change, merge and release are disabled and that no external write occurred. GitHub CI
  run `33850429521` passed 228 Runtime tests, lint and contract audits, real HTTP and all
  offline rehearsals, both architecture builds and the Universal build, including all
  four packaged evidence verifiers.
- Universal artifact `9928305786` has GitHub digest
  `sha256:f855f94f2188ffd37a1dcd74090cc73e2c5b09d6bb0a0513d45da88407ff8202`.
  A fresh repository-external download reproduced that outer digest and bound the exact
  inner ZIP SHA-256
  `39740f8510c913a1393ed375a666776a62247040c85644cdfef730b0e5f366f4`.
  Packaged feedback-export and development-handoff policy SHA-256 values remain
  `96475ba5a2908b74f2e04db512d6c097abe73453d360871cc0149287480c1146`
  and `b4836edda2f612f20b0e7221177d3d346f15eb64887b1eca804d0050dd2bd14e`.
  The independently bound receipt file has SHA-256
  `620fadb1c51e5b27c2e719ac202c026444104726282d790901ff5020e1fbf760`
  and canonical digest
  `84ea954884d232b2013251cf462fcfc8494ec23f6b4ff91b3680cd8434d21427`.
  This closes the current-candidate default-deny packaging checkpoint only. It does not
  perform administrator-authorized export, agent development, human review or a signed
  installed improvement/rollback, so SOP-13 remains `IN_PROGRESS`.
- Still required before `PASS`: administrator-authorized external issue export, agent
  development integration after human triage, independently obtained rather than locally
  supplied review/CI/Apple/installation receipts, a real Developer ID/notarized staged
  update and end-to-end improvement/rollback QA. No feedback may become `released` before
  those facts reconcile.
