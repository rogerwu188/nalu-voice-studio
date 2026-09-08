# Native draft adoption and independent approval

Created isolated fixture with scripts/create-native-story-fixture.py (Ruff and
execution passed). It labels project/content 合成 QA and uses synthetic writer
receipt data; provider execution is explicitly unverified, no model called.
Application Support: `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-story-sp6n8uqp`.
Project prj_902c55a0f1de4e608fce429af4b99414; two episodes.

Used verified arm64 a4a0a06 artifact from CI34272616095 and isolated port18767.
Native actions/results:
- Restored two clearly marked test drafts in conversation.
- Typed 采用第1集草稿 + Return: first episode moved to script_review15%, second
  stayed planned0%; app stated no approval or paid production had started.
- Expanded 剧本创作与确认: complete first test script and approval button visible.
- Clicked 批准当前剧本: first moved to script_approved20%; version marked 已批准.
- Quit: process22061 exited0, owned server29300 shut down, no18767 listener.
- Separate SQLite read: episodes [(1,script_approved),(2,planned)], zero production
  runs. This confirms approval does not implicitly start production or approve2.

This is native workflow evidence, not real writer, semantic script quality,
microphone recognition, production/master or release acceptance. Current app
still exposes professional season/script panels; elderly-oriented simplification
and source/story end-to-end acceptance remain open. No SOP promoted.
