# Read-only listening decision recovery — 2026-09-07

Added GET `/v1/production-runs/{run}/audio-takes/{take}/reviews` with required
expected take digest. Under one SQLite writer lock it revalidates the current
sound/edit, actual decoded recording, consent and current take identity, then
returns the latest per-cue review without writing any events.

The response separates the historical `latest_review` (needed as the next
confirmation's CAS predecessor) from `applies_to_current_take` and `take_approved`.
Changing the recording or source offset cannot inherit a previous acceptance.
Review/take integrity, binding fields and non-final approval flags are validated.
Old-take requests and revoked recording consent fail closed.

Synthetic regression includes absent review, repeated GET after acceptance with
unchanged event count, recovered rejection, an accepted take replaced by a new
offset (old review remains historical but effective approval is false), stale
take reads and consent revocation. Full image workflow: 26 passed in 21.14s.
After tightening historical binding validation, the affected real-encode fixture
passed again: 1 passed, 25 deselected in 21.34s. Ruff, OpenAPI contract check and
diff check passed. No paid calls or releases.

Native recovery consumption, visible confirmation/retry, installed playback QA,
speech alignment, authored final mix, master QA and release remain incomplete.
These synthetic attestations do not prove real user listening. No SOP upgraded.
Parent CI 34101343116 remained in progress when checked; earlier CI 34100009067
passed. This checkpoint requires its own CI.
