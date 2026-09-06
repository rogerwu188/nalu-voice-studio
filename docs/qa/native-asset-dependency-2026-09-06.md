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
