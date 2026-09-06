# Native asset dependency presentation

Tested source bcfc86a / arm64 artifact 9994834005 (CI 34051937128 all jobs
success) in isolated process 80632, port 18769. A native-created project
`prj_57a28cc17a4843879add31a0f43b7029` received a synthetic plain-text fixture
through the local Runtime API. No personal data, provider calls or recording.

Asset `ast_09f41ea02da74407b1345da843ac23e2` retained SHA-256
`bb81f481a903d9efe45b84f44df469abba0b0f4b4a823fde04598bfdcbedc331`.
Reselecting the project loaded the fixture into the native material sheet.
[Native material view](images/native-asset-dependency-before-2026-09-06.png).

**Failed native acceptance:** pressing Check Deletion did not display an alert
on the material sheet. The read-only dependency API returned can_delete true,
zero snapshot references, and an English explanation. The alert modifier was
attached to the underlying root rather than the active sheet. No delete command
was issued; the managed file hash remains unchanged. Cancel acceptance is not
claimed when no confirmation was visible.

Correction moves the alert to the material sheet, uses Chinese typed-status
messages instead of raw service explanations, rejects inconsistent can-delete
reports with snapshot references, and ignores late responses for dismissed
sheets or changed projects. Three native unit tests cover message/deletion
eligibility. Syntax/diff checks pass; new CI and exact native confirmation/cancel
retest remain required. Impeccable hardening guided modal ownership and clear
destructive-action copy, preserving the existing interface.

Separately, two Runtime regression tests pass: referenced assets cannot be
deleted, and stale preflight cannot bypass the transactional dependency recheck.
These do not substitute for native or human acceptance. SOP-05 remains open.

## Native retest on 8af99ac

Exact arm64 artifact 9995048952 from CI 34052638609, archive SHA-256
`7772c6517b069255016d6799ed573dfa33a2ddb56a982b437ab986e331b15c36`
matches its checksum. Bundle/entitlement verification passes (ad hoc only).
Native process 82280 reopened the same isolated database on port 18769; health
reports schema 27. No user data was involved.

- Unreferenced fixture: Check Deletion now presents a nested native alert above
  the material sheet, with Chinese copy, Cancel and Delete Local Material.
  [Screenshot](images/native-asset-dependency-confirmation-2026-09-06.png).
- Escape invokes cancellation, closes the nested alert, and preserves the exact
  fixture hash listed above. No DELETE request was issued.
- Created a synthetic season/episode/script and explicitly synthetic approval,
  then one local dry-run snapshot `run_794d652e8dea459a923f8bc27a34df28` using
  idempotency key `native-asset-dependency-8af99ac-once`. This is not human
  approval, paid video production or true production acceptance.
- A fresh dependency report returns can_delete false and that snapshot ID.
  Native Check Deletion displays the one-snapshot Chinese restriction and
  exactly one button (Cancel), with no destructive action. Cancelling preserves
  the same file hash again.

These native paths pass on the stated binary. Full CI conclusion is still
pending at recording time; model-list advisory, asynchronous project-switch
isolation and whole-SOP acceptance are not closed by this test.

Follow-up settings observation on this binary: initial native settings snapshot
showed OpenAI unconfigured, later changed to stored without a key write. First-open
status freshness needs its own regression. A model-check action was attempted, but
no result was visible at observation; native capability-advisory acceptance remains
open. No microphone session or paid generation was initiated.

Final CI observation: 34052638609 completed success, Runtime, both architecture
jobs and Universal all passed. Only the documented fixture-backed native
confirmation/cancel checkpoint is closed, not SOP-05 or the full product.

## Asynchronous project selection correction

Code review found deletion completion assigned asset/memory lists and appended
messages after awaits without rechecking the current selection. Added a selection
generation (including A→B→A changes), asset ownership check before DELETE, and
generation guards before applying each returned list, success message or error.
Documentary-readiness refresh also rejects stale results. No already-issued delete
is retried or claimed undone; returning to a project reloads authoritative state.

Injected RuntimeClient tests exercise switching at DELETE, assets and memory-card
response boundaries; A→B→A stale error suppression; foreign asset no-request; and
unchanged-selection success. These use URLProtocol fixtures, never real deletion.
Syntax and diff checks pass; full Swift tests/CI and native regression for this
follow-up remain pending. This does not claim all other project-loading methods
are race-free.
