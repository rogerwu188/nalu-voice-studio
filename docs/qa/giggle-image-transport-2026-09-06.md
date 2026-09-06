# QingShan image HTTP transport

Status: IN_PROGRESS. A transport component, not a working image-generation
workflow or paid submission authorization.

Local verification: **442 tests passed in 58.90s**, two existing deprecation
warnings, Ruff passed. Current implementation CI and real provider acceptance
remain unverified; prior evidence-commit CI 34067607241 was in progress.

Protocol basis is the pinned upstream `tools/giggle_asset_factory.py` and
`tools/submit_giggle_character_asset_plan.py`: Giggle text-to-image or
image-to-image, `gpt-image-2-pro`, 1K, one image, `generate_count`, aspect ratio,
watermark false and optional base64 reference images. This is pinned-source
compatibility, not a claim of current provider availability or pricing. Public
documentation search did not return a matching primary reference this turn.

The new transport chooses one of two fixed Giggle HTTPS destinations, preserves
Chinese prompts, forbids unknown parameters and arbitrary reference URLs, bounds
references and responses, disables redirects/environment proxies, verifies TLS,
and strips provider body/credential details from errors. A mandatory trusted
authorization callback receives the durable intent ID and endpoint-bound exact
request hash before HTTP; there is no default callback and no exposed API route.
HTTP acceptance returns only a task identity and hashes, with image_generated
and billing_verified false. Missing IDs, rejected HTTP responses and malformed
or credential-echoing responses are unconfirmed, never retried by the transport.

`tests/test_giggle_image_transport.py`: 16 tests cover both endpoints, authorization
denial before I/O, exact request-hash handoff, missing identity, HTTP failure,
credential echo, duplicate JSON, redirect refusal and unsupported payloads.
All requests use `httpx.MockTransport`; no real account, image, or fee is involved.

Important remaining work: a runtime-owned persistent image intent/receipt ledger
and exact approval must supply the callback. The transport alone does **not**
provide cross-process idempotency. It must not be exposed directly as a paid API.
Reference prefix/encoding checks are not full decoding, identity, consent or
scope validation. QingShan provider-scope projection, entry-state, spatial/camera
and image-model contracts, reviewed costs, task polling, safe media retrieval,
visual QA/lock and native activation remain required. Existing model/video
authorization cannot be reused as image authorization implicitly. No SOP promoted.
