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
