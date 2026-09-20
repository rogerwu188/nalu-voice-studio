# Giggle live-test environment

The explicit campaign authorization is recorded in
`giggle-live-test-authorization-2026-09-20.json`: audio, image and video share
10,000 credits total; publication is excluded.

The first preset-tone-list invocation stopped at Python import with
`ModuleNotFoundError: requests`. No HTTP request or generation submission was
made by that invocation. It was not automatically retried.

Added the optional `live-test` dependency group. Install with
`.venv/bin/python -m pip install -e '.[live-test]'`.
Installation succeeded with requests 2.34.2. `pip check` reported no broken
requirements and the requests import succeeded. Runtime packaging does not
require this optional skill-script dependency.

Remaining before generation: reconcile campaign operations; verify current
prices; implement/use a durable campaign-wide reservation across audio, image
and video. Existing `ImageBudgetService` and `VideoBudgetService` cover a single
run's image/video estimates, not a campaign-wide audio-inclusive charge cap.
The speech skill also requires an explicit voice selection before synthesis.

This environment repair is not API authentication, real media, billing or
product acceptance evidence. No SOP status is promoted.

## Subsequent read-only account verification

`scripts/check-giggle-account.py` made one authenticated GET to the fixed Giggle
credit-statements endpoint using the existing environment credential. It returned
HTTP 200 and validated the successful statement-list response envelope. No key,
account rows or raw response were printed; no generation POST was made. This
proves account statement access, not complete billing reconciliation or sufficient
account balance. The initial check requested only one row.

Campaign reservation and image/SD2 request binding are now implemented through
`GenerationCampaign` factories (43 targeted tests passed at `2c96eb4`). They are
not yet a complete live-test runner or an audio submission integration. Price
evidence must still be verified by the caller; a stored digest alone does not
prove an upper-bound quote. No real-generation result exists for this campaign.

The subsequent bounded 100-row read returned an image Pay observation of 11
credits. Only the event category and numeric amount were emitted, not account
identifiers or raw rows. This historical amount is not tied to the requested
model/resolution and is not a current quote; it must not authorize a guessed
image cost. No audio charge observation was returned by this page. Pagination
and campaign-task-specific reconciliation remain outstanding.
