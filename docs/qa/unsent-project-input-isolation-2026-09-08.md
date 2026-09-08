# Unsent project input isolation

The new typed entry exposed an existing shared-transcript issue: changing project
did not clear or restore the unsent text. Project selection now stashes text and
confidence under its original project and restores the destination draft.
Unselected input has a separate empty-key slot. This cache is memory-only, not a
claim of restart-safe storage; submitted conversation remains SQLite-backed.

Switching project invalidates the recording capture token and stops listening.
Recognition callbacks check their capture token, preventing late data from an
old recording from replacing destination text. Stop and new recording also
invalidate earlier callbacks independently of project reload generations.

Added native project-A/project-B restoration test; awaiting CI and installed
recording/typing QA. `git diff --check` passes. No native execution claimed and
no SOP promotion. Restart persistence of unsent drafts remains separate work.
