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

## Native fix verification (400c621)

CI34276734785 arm64 artifact SHA256:
`89bbd788528872e878eb0436f7b6b49717e7dcaa2d1e19398d1cac3b6e1d4975`.
Swift test steps passed on arm64 and Intel; full CI still running at inspection.
Isolated support directory: system temporary `nalu-project-fixed.ahZaQgsqgt`.
Two Create new project actions produced distinct runtime IDs:
`prj_4b4211adcc6642418d61ab00de08a1dc` and
`prj_110adb548c1c4bcf9304ced907ff2afd` (two POST201 responses).
Typed QA-A未发送故事 in A, created B (input blank), typed QA-B未发送故事.
Clicking A title restored exactly A text; clicking B restored exactly B text.
No Send action/model call was made. App quit afterward.

Remaining UX gaps: duplicate unnamed labels make selection ambiguous and the
row's blank area is not reliably clickable; clicking title works. First row
was partially clipped at1100x736. Unsent drafts are memory-only. This verifies
the narrow creation/isolation fix, not full SOP or restart persistence.
