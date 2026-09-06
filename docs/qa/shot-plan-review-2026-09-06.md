# Local episode shot review

Status: IN_PROGRESS. Backend integration, not native or live-production acceptance.

Initial full run: 418 passed, one concurrent-dispatch test failed because it
selected the first HTTP 200 response as the final result. The competing observer
can legitimately return the persisted pre-HTTP uncertainty marker before the
winning request finishes. The assertion now requires a submitted winner after
both futures join, permits only submitted/uncertain observer states, verifies
the database's final submitted state, and retains exactly-one-provider-POST and
restart replay checks. No production dispatch behavior or safety gate changed.
Final full regression: **419 passed in 53.61s**, with two pre-existing
Starlette/AnyIO deprecation warnings. Ruff and OpenAPI contract checks passed.
Current implementation CI and native QA remain pending.

- `GET /v1/production-runs/{run}/shot-plans/current` returns the newest saved
  draft/revision/approval, or null when none exists. Old events remain available
  as history. Reading history does not make an obsolete plan production-ready.
- `POST /v1/production-runs/{run}/shot-plans/{event}/review` takes the expected
  plan SHA, explicit `revise` or `approve` action, reviewer and confirmation.
  A revision requires a complete structured plan; approval cannot smuggle in
  edits and must approve precisely the stored version. Native conversation-to-
  edit integration is still pending; ordinary users should not fill JSON forms.
- SQLite `BEGIN IMMEDIATE` serializes competing reviews. Stale event IDs and
  hashes conflict. Identical current review requests replay the original event
  after restart. A replay never resurrects an older superseded approval.
- Shared shot validation checks timing, quoted script text, actual package asset
  IDs and exact continuous-state linkage. The current package/run, actual script
  approval and episode duration must still match. Revisions clear approval;
  approved tasks become `awaiting_entry_frame`, not generated or paid-approved.
- Once concrete preparation, estimate reservations or provider tasks exist,
  changing the plan requires downstream reconciliation (not implemented yet),
  rather than silently changing the source of an existing generation request.

The successful synthetic planner scenarios in `tests/test_shot_planning.py`
exercise read → invalid edit rejection → valid edit → version-bound approval →
restart replay → stale edit rejection → downstream preparation lock. A second
scenario carries continuous-shot final-frame dependencies. Reviewing and editing
cause **zero additional model requests**. The fixture is synthetic and uses an
isolated local database. No actual user's project, image, payment or publication
is changed by these tests.

Open: native orchestration/review presentation, voice/text edit mapping, full
camera/prop authority compilation, generated entry frames, binding approved
plan SHA to downstream preparation, explicit downstream revision reconciliation,
real generation/master QA and release. The review record is a creative approval
only; provider authorization and exact-request budget confirmation remain separate.
