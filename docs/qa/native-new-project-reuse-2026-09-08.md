# Native new-project reuse defect

CI34274051972 (98fbf60) passed runtime, arm64, Intel and universal jobs.
Downloaded arm64 zip SHA256:
`d48e78bd68daf4bea252a0325a6286fbd6e626cc8f4eedea5e5419d92adde328`.
Isolated support: system temporary directory `nalu-input-native.IxgCi3SlLP`.

Native reproduction: click Create new project; paste `QA-A未发送故事` without
sending; click Create new project again. Sidebar still has only one unnamed
project, input remains, and conversation changes to the audience question.
This prevented the intended two-project draft-isolation acceptance.

Source confirms beginProject resets the interview and then reselects
draftProjectID when it exists, rather than creating a new project. Fix explicit
new-project behavior while retaining concurrent-click protection. Verify two
distinct IDs and independent unsent drafts afterward. Do not label this QA PASS.
No model request or real-user data was used. App was quit after inspection.

Implementation follow-up: explicit creation no longer reuses draftProjectID;
an in-flight guard suppresses overlapping clicks. The created project is retained
in the sidebar without relying on a second list request. InterviewFlow and draft
project identity now travel together per selected project, like unsent input,
so returning to A cannot rename/finalize B. This state is in-memory only, not a
claim of restart-persistent interview checkpoints. Native tests cover distinct
creation, overlapping clicks, input restoration and project identity restoration.
These tests await macOS CI and a new native artifact; no PASS promotion.
