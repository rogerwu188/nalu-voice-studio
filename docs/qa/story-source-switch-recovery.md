# Interactive story source switching

Scope: switching between an imported novel and the user's narrated story.

- Narrated input excludes inactive novel passages from the writer request.
- The project retains a separate SQLite-owned novel bookmark, outside the
  writer-visible conversation state.
- Returning to novel continuation resumes at the prior character offset rather
  than silently restarting the chapter.
- Explicit chapter requests still override the bookmark.
- Regression uses a 60,100-character source, switches to narration, recreates the
  runtime over the same database, and verifies the remaining 100 characters and
  byte-identical request replay.

This is local fixture coverage, not real provider, installed macOS, human or
release acceptance. Full SOP completion remains unproven.

Combined local regression after 839b5f4: 57 tests passed in 13.85s across novel
imports, interactive story, source-to-review journeys, writer service/API,
writer execution/recovery/backup and production authorization. Progress-file
audit reported no failures; its PASS is a metadata check, not product acceptance.
Latest native CI 35528372766 was pending behind live run 35527966749; no restart
or cancellation performed.

Full local backend regression on the 839b5f4 implementation (documentation HEAD
83a54c5): `pytest -q` completed successfully, 889 passed, 2 dependency deprecation
warnings, 541.98 seconds. Session 97205 exited 0; do not restart it as unfinished.
This includes encoded synthetic production fixtures, not real-provider or human
acceptance. CI35528372766 subsequently started runtime, arm64 and x86_64 jobs.
Direct local Swift typecheck session49181 was still running at this checkpoint;
SwiftPM failed before tests with a PackageDescription linker error. Neither is
recorded as native test success.
