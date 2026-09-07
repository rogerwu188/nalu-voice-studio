# Two-source interactive writing journey — 2026-09-07

Scope: synthetic Runtime HTTP integration, not installed macOS, real-provider,
paid video, final master, or publication acceptance. No SOP status is upgraded.

`tests/test_two_source_writing_journey.py` runs both `narrated_story` and
`web_source` from project creation through two generated episode drafts, a
second-episode-only correction, SQLite restart recovery, writer receipt binding,
explicit script approval and separate dry-run production packages. It verifies:

- Retrieved page text reaches the writer context; source lookup is mocked.
- The second writing request sees existing drafts and the requested correction.
- Changing episode two preserves episode one, including its authoring receipt.
- Restart issues no extra writer request and restores the entire writing state.
- Generated scripts are not automatically approved.
- Each production package contains only its selected, confirmed script version.

Local verification: 31 tests passed in 16.46s across the new journey plus
interactive story, writer bridge/API, source reader, execution and transport
tests. New journey alone: 2 passed in 4.27s. Ruff passed for the new test.
These deterministic fixtures prove orchestration contracts, not model quality.

Parent `998d45e0ac74373bee0acc31dcfafc51e56b0ffe` CI run
https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34100009067
had runtime, Intel and ARM jobs passing; Universal remained queued at this check.
This checkpoint still requires its own CI result.

Remaining mainline: installed two-source interaction and real writer response,
episode production, actual audio/subtitle/master QA and controlled release.
Previously recorded Hops 401 remains unresolved; no new credential prompt or
automatic paid retry was issued. Preserve the existing TTS baseline.
