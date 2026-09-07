# Opening-frame aspect ratio / resolution compatibility

Status: IN_PROGRESS — a source-backed production-request fix, not live output QA.

Read-only checks on 2026-09-07 retrieved the official
[Pro text-to-image](https://apidocs.giggle.pro/449072504e0) and
[Pro image-to-image](https://apidocs.giggle.pro/449072516e0) documentation. Both
resolution descriptions list 1K widescreen/portrait sizes as 1536×1024 and
1024×1536, whereas the corresponding 2K sizes are 2048×1152 and 1152×2048.
Inference from the documented dimensions: the former do not match a 16:9/9:16
project and would fail Nalu's actual-frame ratio check. This does not establish
what a live paid request will return; the published documentation may itself be
imperfect, so the actual received pixels still require verification.

The runtime now automatically selects the lowest documented matching-ratio
profile: 2K for 16:9/9:16, 1K for square and 4:3/3:4. It records resolution and
documented dimensions in the immutable preparation. The concrete HTTP transport
supports bounded 1K/2K and rejects the documented mismatched 1K wide/tall pairing.
It does not crop, relabel or approve received frames to conceal a mismatch.

Changing resolution changes both preparation and request digests. Existing
1K preparations/estimate approvals are not silently promoted to 2K; existing
submission intents remain quarantined against a new POST. Stored results remain
available for read-only inspection, but use against changed preparations requires
explicit reconciliation. No actual paid image was generated in this change.

The [public pricing page](https://apidocs.giggle.pro/8562698m0) retrieved during
the same check listed SD2 video rates, not a usable Pro image unit-price table.
The inspected Pro endpoint pages also did not provide an image unit-price table.
This is a limitation of these inspected sources, not a claim that no price source
exists. Automatic image-price observation remains unimplemented pending an
authoritative applicable source; no numeric image rate was invented. Existing
user-confirmed estimates must not be represented as verified provider prices.

Initial targeted coverage: 56 tests passed in 6.88s. Tests cover all five profile
ratios, rejection of mismatched wide/tall 1K, current-frame preparation, budget
binding and square frame review. Full regression is recorded after completion.
Native, live output, account pricing and full story-to-release QA remain open.

Full local regression subsequently completed: **532 passed in 71.31s**,
including explicit persisted portrait/square profile assertions. Ruff passed;
the OpenAPI contract remained current (no endpoint schema change). CI evidence
for this commit is not yet available at the time of this local test record.
