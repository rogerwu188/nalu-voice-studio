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
