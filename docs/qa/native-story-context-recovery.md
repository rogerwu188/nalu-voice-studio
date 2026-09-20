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
