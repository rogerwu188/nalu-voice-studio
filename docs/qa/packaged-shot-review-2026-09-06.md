# Packaged native shot review — bounded evidence

Candidate: `026dac26ce7b2f18f28904e3f73cc19151471c26`.
[CI 34067090591](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34067090591)
completed successfully for runtime, macOS arm64, macOS x86_64 and universal.
This includes compiled native shot model tests, not only Swift syntax checking.

ARM artifact `9999348523`, 48,193,079 bytes, was downloaded once and extracted to
`/tmp/nalu-shot-review-qa.HEbraL/app/Nalu Voice Studio.app`. Inner ZIP SHA-256
matches its CI checksum file:
`84efbcc831e2b0df7d554d50c7287ac34c87ce4c718246a1d436ba89e61f2f69`.
`codesign --verify --deep --strict` passed. This is an ad-hoc signed QA artifact,
not Developer ID notarization or a completed distributable release.

The first local launch used an invalid QA data root and a port already occupied
by a different source runtime (schema 27). That response was rejected as evidence
for this candidate. Only the newly launched QA app was terminated; the existing
port owner was not stopped. Corrected launch uses the existing downloaded app,
port **18779** and macOS temporary support directory
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/tmp.s6tDIlsUyw`.
Its managed runtime returned schema **28**, created its own `nalu.sqlite3` and
was visibly online in the selected app-path window. Previous user/QA data stays
in its original directories.

Fixture project: `prj_6c73986c20c846e194bd5dd61fa94dee`, visibly named
`[QA 合成] 分镜查看与确认`; episode `ep_c5b55bb3abce427bab24dcd2463620b9`;
run `run_e1de7f4b395447429cfc98dab10968b1`. Actual HTTP created a synthetic
user-authored script, approved it and obtained dry-run preflight. A two-shot
draft event was inserted into this isolated database with explicit synthetic
provenance; **no model generated it**. This tests the native review journey,
not live AI quality or successful Hops authorization.

Observed through native accessibility actions and an in-conversation screenshot:

1. Expanding “本集怎么拍 · 分镜方案” displayed the saved two-shot summary,
   original script excerpt, shot selector, readback and edit/review controls.
2. Editing shot one's description enabled Save, disabled Confirm and displayed
   “您改过内容，请先保存，再确认。”
3. Save returned “修改已保存，请重新确认这个版本。” and enabled Confirm.
4. Confirm returned “本集分镜已确认，下一步准备画面；还没有扣费制作视频。”
   and “已确认 · 等待准备画面”, disabling another confirmation.
5. The actual runtime current-plan endpoint returned approval event
   `evt_eaf209b2b2af41dcac95943173b14d59`, plan hash
   `9d3e0b2b96b305fafea8be2ac6cb3ce89783cc3b26fe241e97e8aa07f11ef4af`,
   approved true, paid_approved false and two tasks. Shot one's saved video
   description contains the requested hand-to-sea composition; shot two remains
   unchanged. The isolated database has **zero remote task bindings**.

The screenshot confirms the existing bottom microphone control remains visible
at the inspected window size. It is conversation evidence, not a saved screenshot
asset or a full large-font accessibility verdict. Speech playback audio quality,
microphone-driven edits, restart UI restoration and the Impeccable finish review
remain pending. No full SOP is promoted to PASS. Next: generated entry frames,
plan-to-complete-professional-request compilation, real provider generation,
master QA and release, plus outstanding native accessibility acceptance.
