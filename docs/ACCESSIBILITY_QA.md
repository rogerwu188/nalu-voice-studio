# macOS accessibility QA

This document records evidence without promoting an automated check into human
acceptance. A green build or readable accessibility tree is not a VoiceOver sign-off.

## 2026-08-29 · Direct family-archive entry

Release candidate:

- commit `c2001b4`;
- GitHub CI run `33286249745`;
- downloaded `Nalu-Voice-Studio-macOS` artifact produced by the macOS job;
- macOS 26.3.1 on Apple silicon.

Read-only accessibility-tree inspection confirmed:

- the main window exposes project rows, Runtime state, the push-to-talk state and
  primary controls as native accessibility elements;
- the family archive control is announced as “选择家庭资料” with the help text
  “直接打开文件选择器，资料名称和归档草稿由 Nalu 整理”;
- after a project is selected, activating that control opens the native macOS `Open`
  panel directly; the intermediate metadata/management modal is not on this path;
- cancelling the panel returns to the interview without importing or transmitting a
  file;
- “管理资料” remains a separate secondary action for existing assets and professional
  authorization controls.

The QA-created project `prj_747472f4e5e5406480d11d30533c53b6` had zero assets and
zero production runs. It was deleted after an exact deletion preview; the Runtime
returned `verified_absent: true`. The pre-existing project was not modified.

## Not yet accepted

- Human VoiceOver traversal and focus-order report.
- Accessibility Inspector contrast, target-size and clipping report in normal, dark,
  increased-contrast and large-text configurations.
- Clean-account microphone and speech-recognition permission journey.
- Older-adult and guardian/child voice-only task completion.
- Authorized Realtime audio, interruption, network-loss and session-expiry QA.
- Developer-ID-signed and notarized release-candidate repetition of this matrix.

## 2026-08-29 · Project library entry

Release candidate commits `21c09a0` and `23dc463`, GitHub CI run `33286805948`.
Accessibility-tree inspection of the downloaded artifact confirmed that a project with
no season or episode plan still exposes “项目人物、场景、道具和声音”. Expanding it
exposes the type picker, name and description fields, disabled-until-valid draft action,
plain-language authority warning and a “用语音添加” menu. The menu exposes 人物、场景、
道具、声音 and 画面风格 as native actions. No library entry was created and no microphone
permission was requested during this read-only pass.

## 2026-08-31 · Packaged semantic-media QA action

Release candidate:

- product commit `c3dbba19511a84ff57e7e223dcd35a58ada1ee38`;
- GitHub CI run `33345468515`, universal job `99349446051`;
- downloaded universal ZIP SHA-256
  `8524df138c1dfaf3a9826cbe9087a45f2bc1c2126b676d3a8ce973b1b45e0153`;
- both the native application and bundled Runtime contained `arm64` and `x86_64` slices.

The packaged application was launched with its own bundled Runtime. A temporary local
project contained one approved episode and one dry-run production record placed in the
`qa_review` presentation state. Its native accessibility tree exposed:

- “第 1 集，正在质量检查，进度百分之 90。Nalu 正在工作，没有停”;
- the secondary action “检查成片声音与转场”;
- the help text “下载当前封存成片，在本机核对中文台词、字幕和镜头切点”;
- visible button copy “只在这台 Mac 上识别；通过后仍需您观看确认”.

Activating the action against the deliberately unsealed run failed before speech
recognition and displayed: “成片自动检查没有完成：无法取得当前封存成片或其校验摘要。
没有改用云端识别，也没有进入发行。” No microphone permission, provider credential,
network speech service or paid production was used or approved. This verifies the
packaged fail-closed presentation path, not acoustic recognition quality or human final-
master acceptance.

The only QA-created project, `prj_e0baa5d807fb4bf4aac0b8253932d2dc`, had zero assets
and one dry-run production record. After an exact deletion preview, the Runtime removed
the run and returned `verified_absent: true`; a subsequent project read returned 404.

## 2026-08-31 · Universal Runtime cold-start and quit lifecycle

Release candidate:

- product commit `d285aa943f55656a221b32270d7275220a58a6b6`;
- GitHub CI run `33349286197`, universal job `99360207521`;
- universal artifact `9743140010`, ZIP SHA-256
  `55f933f188234aff8c051c1a10104c307225134440e203d52f652025ddd1a08f`;
- both the native application and bundled Runtime contained `arm64` and `x86_64` slices.

The preceding `a99dcfc` artifact was deliberately treated as a regression candidate, not
accepted evidence. Its visible state remained “本地制片厂正在启动 → 请稍等” beyond the
old 30-second deadline and then became online at about 70 seconds, proving that a longer
finite startup window was necessary. Cmd-Q then closed the native UI but left both the
PyInstaller Runtime parent and child listening on port 8765. The cause was a termination
notification that enqueued a main-actor Task after the application event loop had ended.
The QA-owned orphan was terminated explicitly; SIGTERM removed both processes and the
listener.

The `d285aa9` artifact replaced that deferred cleanup with a synchronous main-thread
termination signal and added a regression test requiring the callback to run before
notification delivery returns. In a fresh native launch, the accessibility tree changed
from “系统状态：本地制片厂正在启动 → 请稍等” to “本地制片厂在线 → 可以创作”
at about 35 seconds, under the bounded 180-second policy. Process inspection confirmed
that the Runtime belonged to the launched application, `/health` returned `status: ok`,
schema version 14, and the bundled OpenAPI contained the postproduction-lineage QA route.
After Cmd-Q, the native app list was empty in about 2.8 seconds; the exact app, Runtime
parent and Runtime child PIDs, port 8765 listener and `/health` endpoint were all absent.

This pass only read existing local project state. It did not click Realtime, request
microphone or speech-recognition permission, enter credentials, start paid production,
modify a project or publish anything. It verifies visible startup/liveness and owned-
process cleanup, not human VoiceOver, clean-account installation or notarization.

## 2026-09-03 · Current Universal older-adult entry regression

Release candidate:

- commit `a270ab267aa8645559d54064db21fb5d21faa432`;
- GitHub CI run `33812804669`, all Runtime, arm64, Intel and Universal jobs passed;
- Universal artifact `9915641200`, GitHub artifact digest
  `sha256:1290fa1d8b1a8379a2cfcceaa07083c99e14caef0dd3007d333e91ca9cc7fe2f`;
- downloaded inner ZIP SHA-256
  `099d3db88d408151993fa03228115144ec1bfe921401e63b19c23cca4ee022e9`,
  exactly matching the bundled checksum file;
- macOS 26.3.1 (25D771280a) on Apple silicon.

Both `NaluVoiceStudio` and the bundled `nalu-runtime` were confirmed as Universal
Mach-O binaries containing `arm64` and `x86_64` slices. The bundle has an ad-hoc
signature with no Team ID and Gatekeeper rejected it, so this pass is deliberately not
claimed as signed-install, notarization or final release acceptance.

The freshly downloaded application exposed “系统状态：本地制片厂正在启动 → 请稍等”
while the one-file Runtime unpacked. In about 45 seconds the native accessibility tree
changed to “本地制片厂在线 → 可以创作”. `/health` returned `status: ok`, Runtime
version 0.1.0 and SQLite schema 26. Process inspection showed PID 68234 as the
PyInstaller parent and PID 68239 as its child, rather than two independently launched
Runtime instances; only the child listened on `127.0.0.1:8765`.

Read-only/native interaction then confirmed:

- the status, microphone state, large push-to-talk action and project list were native
  accessibility elements;
- “选择家庭资料” opened the standard macOS `Open` panel directly, and Cancel returned
  without importing or transmitting a file;
- the natural-voice sheet explained cloud audio, possible API cost, local-storage
  boundaries and its session ceiling; without a Keychain credential, “同意并开始自然语音”
  was disabled;
- activating “创建新项目” immediately changed the project list from one to two rows,
  selected the new persisted “未命名故事”, and displayed the first single interview
  question asking who would use the application.

The QA-created project `prj_74ce21d73cf34a299687cb4c17d27cbc` was identified by
the before/after Runtime project list. Its deletion preview reported zero assets and
zero production runs. Exact-ID deletion returned `verified_absent: true`, a subsequent
read returned 404, and the pre-existing project remained present. After normal Quit,
the exact application PID 68206 and Runtime PIDs 68234/68239 were absent, port 8765 had
no listener and `/health` refused the connection.

No microphone or speech-recognition permission was requested, no credential was
entered, and no Realtime, paid provider, production or publication call occurred. The
source still binds both message-count and live-transcript changes to the conversation
bottom anchor, but this pass did not generate real speech and therefore does not promote
automatic scrolling, spoken interruption or transcript confidence recovery to human
acceptance. Those checks, the VoiceOver/Accessibility Inspector matrix, a clean account,
Developer ID signing and notarization remain outstanding.

## 2026-09-03 · Isolated native conversation-scroll regression

Release candidate:

- product commit `d1e6fd605633d7dcf7f78a04e7a5573a6df5e41f`;
- GitHub CI run `33815093943`, all Runtime, Apple Silicon, Intel and Universal jobs
  passed;
- Universal artifact `9916452123`, GitHub artifact digest
  `sha256:12a46e059835e612805d53c8f584d97d8954206cb83413500ddd5383fb7375f9`;
- downloaded inner ZIP SHA-256
  `e60126b3fb000424b9d0e6b3f539f376e6768f7ddec0a774327f8a25cc601021`;
- both `NaluVoiceStudio` and bundled `nalu-runtime` contained `arm64` and `x86_64`
  slices.

The exact downloaded application first completed a normal launch and Quit, leaving no
application process, Runtime process or listener on port 8765. It was then launched with
all three explicit isolation values:

- `NALU_ENABLE_LOCAL_QA=1`;
- `NALU_LOCAL_QA_SCENARIO=conversation-scroll`;
- `NALU_LOCAL_QA_APPLICATION_SUPPORT` set to the existing system-temporary directory
  `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-scroll-native-state.6YZqMj`.

The scenario is unavailable in a normal launch. Automated Swift tests require it to
reject a missing local-QA flag, unknown scenario and non-temporary directory before it
can alter presentation state. With the exact isolated launch, the embedded Runtime
became healthy on loopback with SQLite schema 26. Process inspection identified native
PID 71918 and bundled Runtime PID 71937. The latter opened only
`nalu-scroll-native-state.6YZqMj/nalu.sqlite3`; neither process opened the user's Nalu
Application Support project database.

The fixture installed 18 alternating, long interview turns, first presented one partial
transcript and then replaced it after 800 milliseconds with:

> 【QA 当前实时转写】外婆把雨衣披在我身上以后，还笑着说不用害怕。

The fresh native accessibility tree exposed the conversation container as
`nalu.conversation.scroll`, included that final transcript at the current turn and
reported vertical scrollbar value `0.9749780509218613`. A native-window screenshot
showed the latest transcript card, listening guidance and push-to-talk action together;
no manual scroll action was performed. This directly verifies that both long-message
growth and a later live-transcript change remain anchored at the current conversation
content in the packaged application.

Normal application-menu Quit removed PIDs 71918 and 71937, ended the launch session and
closed port 8765. No microphone or speech-recognition permission sheet appeared, no
Keychain credential was read, and no Realtime, provider, paid-generation, production or
publication call was made. This is deterministic packaged native regression evidence;
it does not replace a real-microphone session, VoiceOver traversal, Accessibility
Inspector matrix or older-adult/guardian-and-child human acceptance.

## 2026-09-06 · Stable primary-control accessibility selectors

Product commit `18fac0ba6b7529b4c11c5dab39dded259ff59161` assigns stable,
unique identifiers to the primary older-adult interaction surface:

- `nalu.projects.list` and `nalu.projects.create`;
- `nalu.status.runtime`;
- `nalu.voice.realtime`, `nalu.voice.activity` and
  `nalu.voice.microphone.toggle`;
- `nalu.assets.import.toolbar` and `nalu.assets.import.card`.

GitHub CI run `34008547788` passed the Runtime suite, both architecture-specific
Swift suites and application builds, bundled smoke tests and Universal merge. The new
Swift test rejects duplicate, whitespace-bearing or non-`nalu.*` selectors. These
identifiers let future Computer Use and Accessibility Inspector runs address controls
without depending on translated button text.

The Universal artifact is `9981803874`. A repository-external download reproduced its
GitHub artifact SHA-256
`6b8dc142859ca001bfb2ede5b8c39d79dd37f1fc073a6fdb436e212e42bc5225`;
the inner application ZIP SHA-256 is
`e807b309cb57e7526eee20bb6744a74ec0d1d6a2af38c0abaae0c1a3e11126d2`.
The extracted `studio.nalu.voice` application is version 0.1.0, its native executable
contains `x86_64` and `arm64`, and a packaged-binary scan found all eight identifiers.
The CI artifact remains ad-hoc signed with no Team ID and is not a release candidate.

The Mac was initially locked when the freshly built window was ready. After unlock, the
exact downloaded application was relaunched against an isolated system-temporary SQLite
directory with the `conversation-scroll` fixture. Its native tree exposed all eight
identifiers. The latest live transcript was visible at scrollbar value
`0.9308466051969824`; activating `nalu.projects.create` immediately added the selected
“未命名故事” row; `nalu.assets.import.card` opened the native file picker and Cancel
returned without importing; and `nalu.voice.realtime` opened consent copy promising to
answer an interruption before returning to the flow while its start action remained
disabled without a Keychain credential. Runtime health reported schema 27.
Normal application quit then removed the exact app and Runtime parent/child processes
and closed the loopback listener.

Machine-readable evidence is
`docs/qa/native-accessibility-selectors-2026-09-06.json`. No microphone permission,
live Realtime, VoiceOver human traversal or paid call was exercised, so those acceptance
items remain open.

## 2026-09-06 · Recording-waveform motion contract

Product commit `b8d2bc50802918e467fc99e7488d98285df53a90` moves the listening
wave calculation into a testable presentation primitive. Its regression suite samples
all five bars across 201 time positions, requires every level to remain in the renderable
zero-to-one range, and requires two frames 0.12 seconds apart to differ visibly rather
than silently degrading to a static red icon. The isolated long-conversation fixture also
enters the listening presentation without starting `SpeechRecorder` or requesting a
microphone or Speech permission.

GitHub CI run `34009992117` passed 81 XCTest tests on each architecture, including both
waveform tests, as well as the complete Runtime, arm64, Intel and Universal jobs.
Universal artifact `9982225088` has GitHub archive SHA-256
`3d3ae54199a9be6c41ae221debd81cb5279ee216f57a73a76a299d87efbc02d6`;
a repository-external download reproduced that digest and its declared inner ZIP
SHA-256 `1c1610af6001e9e0c74f6a3dac8c0ace825473884466eece3db878a98e0acc67`.
The extracted `studio.nalu.voice` application and bundled Runtime contain both `arm64`
and `x86_64`; the application remains ad-hoc signed with no Team ID.

The exact artifact first launched against the isolated system-temporary directory
`nalu-active-current.QCWNCJ`, and its loopback Runtime returned version 0.1.0 and SQLite
schema 27. After the macOS session was unlocked, the same artifact was replayed against
the separate isolated directory `nalu-active-current-replay.X7qoXI`. Its native tree
reported `nalu.voice.activity` as “正在录音，Nalu 正在听”, exposed the microphone action as
“说完了”, kept the final live transcript visible and reported scrollbar position
`0.9316275167785235`.

Two native frames 0.6 seconds apart visibly changed all five waveform bars. A crop limited
to the status area contained 85,800 pixels; 1,827 pixels changed, with the changed region
bounded to the waveform rather than the surrounding copy. The user independently reported
seeing the red animation. Normal application Quit removed native PID 43873 and Runtime
PIDs 43902/43910, closed port 8765 and made `/health` unreachable. Exact frame/crop hashes,
pixel comparison and process facts are recorded in
`docs/qa/recording-waveform-contract-2026-09-06.json`. This closes deterministic and
native visible motion for this fixture, not real microphone input, VoiceOver,
Accessibility Inspector or older-adult/child human acceptance.

## 2026-09-06 · Native project restart, backup and clean restore

Packaged native QA first reproduced a real failure: the existing SwiftUI project exporter
and importer controls did not reliably present their macOS panels. Commits `7e23928`,
`1a1fb55` and `10cc1df` replaced backup with an AppKit `NSSavePanel`, atomic file write
and a plain-language completion alert. Commit
`2e1a4e5ceebf6226b52c94cfd178bfc07344bb7f` replaced project restore with an AppKit
`NSOpenPanel` and security-scoped JSON read.

GitHub CI run `34015343605` passed 291 Runtime tests, 84 XCTest tests and 29 Swift
Testing tests on each architecture, both application builds, the Universal merge and all
packaged isolation/update/rollback rehearsals. Universal artifact `9983831769` has GitHub
artifact digest
`sha256:b817bd048053c7efb6f164fcdfbf6958d2bda472042e8aaa0fe132f653afe920`.
The downloaded inner ZIP reproduced its declared SHA-256
`adf0d524466c41b5458ab6dc117ab6fd9c7d7abfa3045cc201cd6ee12dcc6d86`;
the application contained both `arm64` and `x86_64`, remained ad-hoc signed and had no
Team ID.

Against an isolated system-temporary SQLite directory, the renamed project “海边的外婆
（原生重启 QA）” survived a normal application restart. `nalu.projects.backup` opened
“保存项目备份”, saved an atomic `nalu.project-export/v23` JSON file and showed a
plain-language success alert. The backup SHA-256 is
`656f8914ca1480c8e86092248026855ff996f3b3b0cec8e5e5d650b05070aea2` and its
payload digest is `c561c199d31fd4b3aeefd7a2d39fa61143edac69d4638d736c0b21da728c6081`.

The exact final Universal artifact then started against a second, initially empty SQLite
directory. `nalu.projects.restore` opened “恢复 Nalu 项目”, limited selection to JSON,
and restored the backup with the success message “项目已经恢复，可以继续讲故事了。”
The native project row and Runtime API both retained project ID
`prj_e45f6c75eb284703b709a066f5bd92bd`, title and six-episode plan. The source database
SHA-256 remained
`7a4d80d5b8a3392742bbe5a6f02eff13db6b75f0e44994260d2e5e480199be3c`.
Normal Command-Q removed native PID 53368 and Runtime PIDs 53418/53423, closed the
loopback listener and made `/health` unreachable.

A later persistence recheck overlapped with the user's live foreground interaction. No
transcript from that interaction is retained as evidence, and this pass makes no blanket
claim that the microphone was unused. No credential, paid provider, production or
publication operation was performed. Exact facts are in
`docs/qa/native-project-persistence-2026-09-06.json`. This is native project-transfer
evidence, not a clean-account VoiceOver or older-adult/guardian-and-child human pass.
