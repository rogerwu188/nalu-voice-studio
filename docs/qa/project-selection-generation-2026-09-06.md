# Native project-load response isolation

SOP-03 / SOP-05 remain IN_PROGRESS.

Inspection found that `selectProject` published each awaited response directly
without checking whether a different selection or newer reload had superseded it.
That could place old assets, memories or episode data under a new project title.

The follow-up rotates the selection generation on every project load (including
same-project reload), clears old project lists and episode/script selection before
waiting, and checks the generation after every awaited project/season response.
Publication-learning completion and loading flags are guarded by that generation
as well. This does not prove all other async view-model methods race-free.

Regression tests inject project switches at asset, memory, library and season
response boundaries; assert old assets are absent while waiting; cover A-B-A and
a nested newer A reload. No network, real asset deletion or provider calls are
used by these fixtures. Local Swift syntax and diff checks pass. Full compiled
Swift tests, CI and native rapid-switch QA remain open. Existing paid/real E2E and
signed release gates are not satisfied by these fixtures.

## Exact-artifact native check

Source `4e03c16a16183eaaf53f7ee9a0582ee3b1457614`, CI `34054486473` all jobs
passed; arm64 artifact `9995568082`, ZIP SHA-256
`830baa0275a3932f58cbd0139f3693d62173ff90b0faec159a8e76618fb47cdf`.
Native process 86544 used the existing isolated data/port 18769. Project A
`prj_57a28cc17a4843879add31a0f43b7029` contains `Synthetic-QA-only`; synthetic
project B `prj_c23554a23adf4cdca88394196f7d3349` contains no assets.

Native sidebar selections followed by Manage Materials showed B empty, A with
the expected asset, then B empty after five consecutive B-A-B-A-B clicks. The
[final window](images/native-project-switch-empty-2026-09-06.png) matches the AX
readback. No asset was deleted and no provider call occurred. This native check
uses normal localhost timing; injected unit tests, not this observation, cover
deliberately superseded responses. Whole multi-project/season/episode human E2E
acceptance and the broader SOP gates remain incomplete.
