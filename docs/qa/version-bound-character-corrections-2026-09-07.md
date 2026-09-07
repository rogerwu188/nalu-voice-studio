# Version-bound character corrections

IN_PROGRESS. Correction API and native request encoding are prepared; the spoken
correction state machine and real UI acceptance remain unfinished.

The library revision endpoint accepts optional `expected_current_revision`.
SQLite now serializes revision allocation and checks that heard/reviewed version
before saving. An immediate identical request replays the same next revision;
different stale content and obsolete replays are rejected. Existing confirmed
history remains intact, and the new revision needs separate confirmation.
Legacy requests remain compatible. Entity creation and response models do not
acquire a request-only expected-version field.

Evidence:

- `tests/test_project_library.py tests/test_shot_planning.py`: **23 passed in 37.55s**.
- New test covers restart replay, name whitespace normalization, preserved
  confirmed version, stale different correction, competing concurrent corrections
  (one wins, one conflicts), and rejection after a later revision.
- Ruff, OpenAPI export/backward compatibility and diff checks passed.
- Swift request encoding test added for exact expected revision, retained source
  photo/memory IDs and no confirmation fields. Awaiting current CI execution.
- Previous native handoff `7f97adc` full CI
  [34076575924](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34076575924)
  succeeded; `87087e7` full CI 34076128700 also succeeded. Neither proves current
  native correction behavior or signed real-E2E product completion.

Next: voice correction → new version → readback → explicit confirmation; then
immutable production-snapshot reconciliation and actual asset/frame/video handoff.
No model/provider/payment/publication call was made. No SOP promoted to PASS.
