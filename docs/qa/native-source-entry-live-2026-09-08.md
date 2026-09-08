# Installed native source entry: real public download and pause

Tested arm64 artifact from CI34272616095 / commit a4a0a06 (not latest main).
ZIP SHA256: `fbad11704e195932fb0ce55d4e271ec457d65a36762544517a6604cba64c8c2e`.
App: `/tmp/nalu-source-ui-4IOOij/extracted/Nalu Voice Studio.app`.
Isolated Application Support: `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/tmp.cfau4gdCJQ`.
Port18767; NALU_ENABLE_LOCAL_QA=1. No user installation/data replaced.

Using native accessibility actions:
1. Click Create Project: sidebar immediately showed 未命名故事.
2. Paste `导入小说 https://zh.wikisource.org/wiki/西遊記` into
   nalu.conversation.text-input; Send changed from disabled to enabled.
3. Click Send: field cleared, real progress displayed 3/100 chapters saved.
4. Paste 暂停抓取 and press Return: busy indicator disappeared; conversation
   confirmed pause and13/100 saved. This used no model key or paid writer.
5. Screenshot inspection at1100x736 showed microphone, text entry and Send all
   visible below the scrollable conversation. Blank Send was disabled.
6. Quit with Cmd-Q; application process61792 exited0, owned server28546 shut
   down and no port18767 listener remained.

Project: prj_aa9db80f472744a3a8b0a2aa35d4c227. Preserve the isolated database for
restart/resume QA. Still open: restart, large-type layout, VoiceOver, true writer
drafts/video/release. Pause response still appends an unrelated audience question;
this should be corrected in the core conversation flow. This is partial native
evidence, not full SOP completion or verification of later f03b05e draft isolation.
