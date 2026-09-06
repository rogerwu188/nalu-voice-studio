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
