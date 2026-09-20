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

## Installed adoption follow-up (263443a)

CI35532371231 arm64 and Intel jobs passed; runtime/universal were still running.
Installed arm64 artifact10611304583 in `/tmp/nalu-adoption-qa-6TsVDR/app`.
ZIP SHA256 `e5ff00004d331e818c9042729347c9601edeb25d3132bce3a33299c584766bd1`
matches the CI checksum. Runtime18771 uses only temporary fixture directory
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-story-vzy6orpu`;
launch-only invalid model endpoint prevents paid writer requests.

In native UI, submitted `采用第一集草稿`: episode one reached script review15%,
with explicit not-approved/not-producing confirmation. Selected the independent
second project and observed its blank story and planned0% state. Returned to the
first project, which restored episode-one review and both synthetic drafts.
Submitted `采用第二集草稿`: episode two reached script review15%, proving the
first adoption did not leave a blocking busy state. AX row clicks did not select
reliably; screenshot-grounded clicks and list keyboard selection did.

Read-only runtime checks found exactly revision one, approved_at=null, for both
`ep_0925e0367e154662a4c2d7c926438d4b` and
`ep_2aa6ef0a8437434581aee4f8bc32ec74`. The independent project's episode
`ep_cab2171fcf534276b6af6366babc9f71` still has no scripts.
This verifies sequential adoption and project-switch recovery with synthetic
drafts. Deliberately delayed mid-request switching is covered by native tests,
not this manual run; app-restart recovery and actual model generation remain
separate checks. No SOP completion or real film acceptance is claimed.

### Same installed candidate: restart and adoption replay

Normal Cmd-Q removed the tested app PID5717 and owned runtime PIDs5789/5790;
port18771 no longer listened. Relaunched the same263443a bundle with the same
temporary support directory and invalid model endpoint. Native UI restored both
episodes at script_review15% and the two saved synthetic drafts. Sent
`采用第一集草稿` again: success returned, without a stuck busy indicator.
GET scripts still returned only revision1 with original creation timestamp
2026-09-20T19:36:53.096702+00:00 and approved_at=null. GET production-runs returned
an empty list. No duplicate revision, approval or production job was created.
CI35532371231 universal also passed; runtime and local full test session20560
were still running (local progress exceeded80%). Real provider/human acceptance
remains outstanding; this closes only the synthetic native restart/replay check.

### Native manual revision reaches subsequent writing context

In the same263443a installed UI, expanded script review and saved revision2:
`【合成 QA 手动修订】小夏收起红桶，和爷爷一起回家。` with summary
`修改同行人物为爷爷，结尾回家`. UI retained revision1 and showed revision2.
Submitted `按照刚才修改的爷爷回家结尾，继续下一集`. With the deliberately invalid
launch-only endpoint, UI reported writer failure and preserved prior content.
GET interactive-story returned revision4 and the same input, web_source,
writer_failed. Its planning_context contains latest_review_script revision2 with
the exact corrected content and summary; approved_script_revision remains null.
This proves native editing-to-persisted-context handoff, not successful model
execution or generated-content quality.

Local full test session20560 completed exit0:895 passed,2 dependency warnings,
708.72seconds. It ran on263443a product/test code (subsequent changes were only
evidence documentation). Do not restart or poll this completed session.

### Native revised-script approval to preparation

In the same installed263443a fixture, clicked `批准当前剧本` with revision2
visible. UI labelled revision2 approved and episode one ready20%; episode two
remained unapproved15%. Typed and sent `开始本集制作`. UI first reported local
checks/no charge, then preflight passed30%, explicitly not generating video.
GET returned exactly one run, `run_359f45fa9d744d17a01be209fdb5766b`, status
preflight, dry_run=true, error=null. Its production-package.json under the isolated
fixture data/runs directory contains approved_script.revision2 and the exact
manually revised grandfather/home ending, not the old grandmother/dock text.
This is installed script-to-preparation evidence only, not actual video creation,
provider execution, human quality approval or publication.

### Candidate CI and next production boundary

CI35532371231 on263443a completed success for runtime, arm64, Intel and universal.
The installed native shot-plan disclosure shows no saved plan and offers
`生成本集分镜`; it does not claim the preflight is a completed storyboard.
Source inspection confirms generation validates the configured Hops endpoint
before reading the key and calls the model only through the explicit generation
action. No generation action was taken in this check: paid writer authorization
is unanswered and the historical Hops401 has not been retried. Successful real
storyboard generation is still missing, as are actual video and release acceptance.

### Unsaved approval protection (not yet installed)

Inspection found approval selected the latest saved revision without checking
the editor's current text/summary. Added a pre-transport guard for matching
episode, viewed revision, content and summary; mismatches preserve edits and
ask the user to save/view the latest version. Native regression covers each
mismatch and rejects any runtime transport access. This new change awaits native
CI and installed validation; the successful263443a evidence above does not cover it.
