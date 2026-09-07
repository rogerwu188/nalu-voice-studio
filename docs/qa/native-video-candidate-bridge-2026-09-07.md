# Native video candidate bridge — IN_PROGRESS

Added typed native calls for querying an existing provider binding and materializing
a completed result. Query credentials go only to the owned runtime query route;
materialization carries no provider key and never calls generation submission.
Both responses are checked against the current run, task and observation. Pending
results, out-of-range indexes, foreign receipts and acceptance/billing mutations
are rejected. Download recovery remains distinct from generation retry.

Validation:

- Backend video download/materialization and goal-progress regression: 30 passed,
  5.75 seconds. Fixtures use synthetic media; no provider generation was performed.
- Native URLProtocol test added for exact routes, credential isolation, foreign
  identities, pending results and missing indexes.
- Local `swift test --package-path apps/macos --filter EpisodeShotPlanTests`
  failed before source compilation: installed PackageDescription manifest linker
  symbol mismatch. Native test result awaits GitHub macOS CI, not claimed PASS.
- Parent 5186ad1 CI run 34086218843 was still in progress when checked.

Still required: connect these methods to native playback/review, visually test the
installed app, implement accepted tail-frame handoff and perform real episode QA,
master acceptance and controlled release. This bridge does not close any SOP.
