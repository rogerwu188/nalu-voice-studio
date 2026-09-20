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

## Saved candidate selection after restart

In the same isolated project, public story endpoints saved an explicitly synthetic
candidate pointing to the already imported `https://example.com/qa-novel`, with
writingRequested=true. This was fixture preparation, not a search result.
After a normal app quit, both its PID and runtime18770 listener disappeared.
Relaunched with the same isolated directory and invalid endpoint override.
The native conversation restored the synthetic candidate prompt.

Entered `选择第一个` and clicked Send. UI displayed saved1/1 chapters and then
the expected writer failure. GET confirmed revision8: the import turn answered,
the subsequent writing turn writer_failed, both web_source with the selected URL
and retained request to generate episode drafts; one source passage remained.
This verifies candidate recovery, explicit selection and import-to-writing handoff.
The import reused an existing synthetic source, so it does not prove fresh network
download, real search/provider execution, or successful script generation.

UI automation initially timed out. App sampling showed its main thread waiting
in the event loop, and runtime reads remained responsive. Recreating the automation
session restored control; no force-kill or data deletion was used.

## Completed regression

CI35530639796 for fa878a7 completed successfully: runtime, arm64, x86_64 and
universal jobs all passed. Local full `pytest -q`, started at e7cdafa (no backend
implementation or test edits during the run), completed session87056 with exit0:
895 passed, two dependency deprecation warnings,1372.71 seconds. Do not restart
this completed run as pending. These technical checks do not establish successful
real-provider generation, human content acceptance or signed/notarized release.

## Reviewed script to subsequent writing regression

Extended `test_story_to_review_journey.py` across narrated story, web source and
novel import: generate drafts, manually revise/approve episode one, prepare a
dry-run production package, restart, then request a changed episode-three opening.
The intercepted writer HTTP request contains the latest approved revision two
and its exact corrected ending, while episode two retains revision one. The
mocked answer updates the third draft without changing either saved script or
the frozen production package bytes. Approving revision two intentionally clears
revision one's approval timestamp; the test snapshots that superseded state.

Targeted story journey, story context and writer service suites: 14 passed,
two dependency warnings, 6.71 seconds. Ruff and diff checks passed. This is
mock-provider request/response and persistence coverage, not proof of real model
obedience, real video generation or native UI acceptance. CI35532010023 on
ed9c693 was pending when checked; no SOP status was promoted.

## Native adoption project-switch follow-up

c7eb603 adds generation checks between adoption's asynchronous reads/writes and
an isolated delayed-read success/failure test. Further inspection found that its
success path reloads the project, which also replaces the generation token.
The follow-up clears the owned activity before that reload, passes an explicit
reload token, and checks it before selecting the adopted episode or announcing
success. Thus a late reload cannot announce success in a subsequently selected
project. Already-dispatched writes remain scoped to their original project;
this does not claim network cancellation or rollback.

Local `swiftc -frontend -parse` could not validate the change: the installed
CommandLineTools report duplicate `SwiftBridging` module definitions. Native
compilation/tests and installed QA remain pending on GitHub CI. Diff checks pass;
no native test or SOP PASS is claimed for this follow-up.
