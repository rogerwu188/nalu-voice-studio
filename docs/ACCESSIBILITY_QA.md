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

