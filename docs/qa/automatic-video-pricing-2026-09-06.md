# Automatic observed-price estimates

Status: IN_PROGRESS, not real video or billing acceptance.

The runtime reads the fixed public [official pricing page](https://apidocs.giggle.pro/8562698m0)
using bounded, credential-free HTTPS GET, no redirects or environment proxy.
The parser requires unique Pro/Fast table rows and consistent USD/Credits units;
login/error pages, duplicate tables and changed units fail closed. Rates are not
hard-coded. Real public-page check on 2026-09-06T23:02Z returned HTTP 200 and
parsed Pro=26 and Fast=22 Credits/second. No account access or generation occurred.

The preparation-specific `price-observations` endpoint computes the current
concrete SD2 Pro image request's duration × rate, with exactly one output. It
records preparation/request hashes, source URL and response hash, observation
time and a 24-hour expiry. A budget approval may reference the resulting event;
then the exact request, amount, digest and freshness must all match. Existing
reservations cannot silently switch to a different quote.

73 pricing/boundary tests passed: table validation, HTTP failure, correct
six-second 156-credit calculation, expiry and amount mismatch, plus earlier
budget concurrency/recovery coverage. Ruff passed and OpenAPI regenerated.
Full regression/CI and native confirmation remain to verify.

Follow-up: full regression on `7ea32094b595d7261c94c822bc977c42aaf9a86f`
passed 401 tests in 50.28 seconds; OpenAPI freshness check passed. Pushed
[CI 34065785277](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34065785277)
was pending at inspection. Native confirmation and real dispatch are still open.

Published-price observation is not an account-specific binding quote or a
provider-enforced charge cap. These receipts remain `generation_performed=false`
and `provider_charge_cap_guaranteed=false`. Old manual estimates do not acquire
observed-price evidence. Paid dispatch must still revalidate current approval,
script, package, reservation and quote immediately before its durable single
attempt. Native orchestration, actual AI/upstream shot planning, first-frame
generation, media QA and release remain incomplete.
