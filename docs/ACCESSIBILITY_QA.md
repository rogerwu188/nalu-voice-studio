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
