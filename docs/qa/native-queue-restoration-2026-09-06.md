# Native queued-input and two-episode restoration

Status: bounded observations only; SOP-04 remains IN_PROGRESS.

Downloaded arm64 artifact 9997166591 from run 34059690907, product commit
cf674a950e831181905c61eac36adbf18a4d4578. ZIP SHA-256:
`6edd2300c510c66265c49beadc6b5524ee55a2be80fd488001155de592c9e2a2`.
Included checksum matched; `codesign --verify --deep --strict` passed. This is
ad-hoc signing, not Developer ID notarization.

Launched via Launch Services from `/tmp/nalu-queue-app.9CBYTS/app` with isolated
support directory `tmp.gEDfvkaLEc`, port 18769. SQLite backed up before restart
to `/tmp/nalu-queue-app.9CBYTS/pre-upgrade.sqlite3`. Packaged health returned
OK/schema 27 after startup; no restart was forced during startup delay.

Observed native accessibility state after selecting actual project buttons:

- Four existing projects appeared after restart.
- `[QA] 故事恢复验证` restored its synthetic episode script and lookup-failure
  history. A synthetic `queue_only` input inserted through its packaged HTTP
  API appeared as “合成排队验证：外婆当时拿着一把蓝色雨伞。” followed by
  “这条补充已保存在本机，等待编剧处理。”
- Switching to `[QA] 打包编剧凭证双集` removed that other project's queue text
  and showed both synthetic drafts plus separate episode indicators, each
  “等待确认剧本 · 15%”. Neither was represented as paid video generation.
- Local dictation/TTS remained selected and the bottom microphone button was
  exposed in accessibility state.

No model request, script approval or production was triggered by this QA.
Queue insertion used HTTP, not live simultaneous microphone input. Native
adoption-command execution, web queue dispatch (newer commit), concurrent
dictation timing, real writer authorization and full video/release acceptance
remain open. The restored lookup history was preserved, not rewritten.
