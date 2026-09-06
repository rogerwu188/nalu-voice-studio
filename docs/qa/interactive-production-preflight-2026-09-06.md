# Interactive script to production preflight

Status: IN_PROGRESS; local preflight is not video generation.

In the cf674a9 packaged runtime, the previously approved synthetic episode
`ep_7b911d1b2d7041e1b3267be741c5aa2c` created dry-run
`run_ef4b8488a736470885d58e91e40b90af`, using explicit idempotency key
`synthetic-interactive-preflight-sep6-v1`. HTTP 201, state `preflight`.
The QingShan report records upstream v2026.09.05.2 / 401111636a2386c7f087d8dd2ff9df5c0cb98455,
registered compiler selection and capability integrity, with
`paid_execution_enabled: false` and `registered_tests_executed: false`.
This does not establish all upstream tests, provider execution, video or release.

Inspection found the package copied the complete `nalu_interactive_story_v1`
working cache from the project bible, including other unapproved episode drafts
and raw writer answers. New packages now omit that internal namespace while
retaining other project bible entries, the approved episode script and its
separate reconciliation records. Local interview state and project backups are
not erased. Already materialized packages are immutable and are not rewritten.

The two-episode regression now approves episode one, creates a real local
dry-run package, checks the ordinary bible setting and approved script are
retained, checks the working namespace is absent, and reloads both local drafts
plus the original answer. Six interactive-story tests and Ruff passed locally.
Full suite, packaged validation of the change and CI remain separate gates.

Full suite result: 328 passed, one progress-audit failure caused by the prior
abbreviated `observed_head`. Corrected that field to a full existing commit and
reran all six progress-audit tests successfully. Do not label the original full
run green; a fresh full CI run and packaged verification are still required.

Fresh local rerun on e623f12f9c059245ee8287ec83864ceef5632b60:
329 tests passed (50.08 seconds); standalone goal-progress audit passed with
`project_complete: false`. This closes the local abbreviated-commit regression,
not the pending packaged/cross-platform acceptance.
