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
