# Native character confirmation to refreshed production context

Status: IN_PROGRESS; source integration, not native or full production acceptance.

The existing “核对本集人物” action now carries the exact run identity into the
spoken confirmation queue. Before adopting that queue the client reads the run
and checks its project, then checks all requested character IDs. Already-confirmed
characters are skipped. When the queue is empty, the client reads the local
snapshot-refresh preview, posts only if needed, then reloads the exact approved
plan before announcing success. No model/provider key is read for these calls.

Project-selection generation guards prevent stale responses from changing another
project's conversation. Failures retain confirmed characters and scripts; the same
existing character-review action retries without asking for another story or key.
The server's version-bound operation handles restart after a committed refresh.

The episode panel gets a refresh revision signal rather than being destroyed and
recreated. It reloads when idle with no edits; unsaved edits stay visible. Pending
reload hides old frame/reference preparation controls and disables approval/card
preparation. Explicit saved-version reload clears that state. No new form or
visual redesign: Impeccable hardening guidance was used for error recovery and
preservation of user work, with incumbent native large controls and local TTS.

Evidence:

- New native tests cover GET/POST/GET ordering, unchanged GET/GET behavior, no
  model/provider headers, foreign-run/unapproved-response rejection, and preserving
  unsaved edits while preventing stale preparation.
- 22 related backend snapshot/library tests passed in 11.34s; Ruff/diff checks passed.
- Local `swift test --package-path apps/macos --filter EpisodeShotPlanTests` failed
  before source compilation: installed PackageDescription manifest linker symbol
  missing. This is NOT a passing native test. Current GitHub Swift CI is required.
- No actual UI screenshot/readback acceptance, live model, provider generation or
  publication was performed for this checkpoint.

Next: verify native CI and user-visible handoff when desktop access is available;
continue reviewed reference/frame evidence into concrete per-shot video dispatch.
Full narration/web-source-to-script-to-master/release acceptance remains pending.
