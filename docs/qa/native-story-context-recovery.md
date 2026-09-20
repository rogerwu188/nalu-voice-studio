# Installed story context recovery

Implementation: f424efe0d7a91a70cc886e4c73b6811ec6fd5152.
CI run35529945913 arm64 artifact10610867787. ZIP SHA256
`ec86b6ff9a7b25905a9d013a7f0683332b212dd43c257384575bdbe68f8996e7`
matches the artifact's checksum. Both architecture build jobs passed; full CI
was still running at observation. This is not evidence for later source lookup fixes.

Installed app: `/tmp/nalu-story-context-mYsyyQ/app/Nalu Voice Studio.app`.
Isolated support directory:
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-story-a_wcxcpq`.
Project `prj_51b106df9442429a9268d8a45b38d3cc`, runtime18769.
Launch-only `-nalu.ai-service-base-url invalid-local-qa` prevents model requests
before credential use. Fixture chapters and two drafts are synthetic.

Native accessibility UI restored the project and both episode drafts. Entered
`继续下一集` in the native text field and clicked Send. UI reported the writer
request did not finish, existing content was retained and no automatic retry ran.
GET interactive-story confirmed revision4, last text `继续下一集`, web_source,
writer_failed, two retained drafts and one novel source passage. Its frozen
planning_context contained this project's title, planned_episode_count2,
target_episode_seconds150 and one season.

This proves installed routing, planning-context recovery and failure preservation.
It does not prove successful model generation, spoken input, first-import reuse,
current-HEAD native QA, real content quality, production or release acceptance.

## First adaptation with no writing history

Implementation fa878a76fbff4d4a4e3489c011f460aa3cdc20cb, CI35530639796,
arm64 artifact10611800055. ZIP SHA256
`680cf82b5e97a1a0f4b57e6ec076c329fe3ffad9625f7b092fcdd387125dc709`
matched the supplied checksum. App `/tmp/nalu-novel-choice-0peIC8/app/Nalu Voice Studio.app`.
Import-only fixture support directory
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-story-7tmlyoc_`,
project `prj_9830408cd3504efc8d66b6f5fee69eb8`, runtime18770.
Fixture creation verified empty turns and no novel_source before launch.

With the same invalid endpoint launch override, typed `把这本小说改编成短剧`
and clicked Send. Native UI reported writer failure, not a lookup response.
GET showed exactly one turn, revision2, web_source/writer_failed, zero drafts,
and the complete25-character synthetic first chapter with SHA256
`0380e79d7414e747060f51079abe46a8a44a0842b61a2f7a63f8c24591dd3050`.
This verifies first adaptation uses the saved import even without prior writing
context. No real writer call, paid generation, search-result selection, speech
recognition or final content acceptance is claimed.
