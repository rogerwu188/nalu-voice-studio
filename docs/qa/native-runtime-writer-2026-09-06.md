# Native to runtime writer activation

Status: IN_PROGRESS. Implementation follows backup checkpoint
`63dc22d427d13855d343b69be47b8bb8c715bb61`.

For the configured `https://hopsapi.com/v1` endpoint, native narrated-story
input now calls the local runtime generation endpoint after persisting the turn.
The runtime owns the prompt, fixed Hops destination, durable invocation ledger,
response validation and draft persistence. The native client passes the existing
Keychain credential transiently, never in the JSON body. Other configured
providers retain their previous path; Hops failures do not trigger fallback.

The endpoint accepts only model and expected revision. Browser Origin requests,
missing credentials and extra destination fields are rejected before transport.
Tests use injected MockTransport, not real provider calls: valid response creates
drafts and receipts, duplicate invocation is blocked, a 401 is sanitized and is
not retried, and credentials are absent from persisted ledger values.

Four endpoint/service tests, Ruff, OpenAPI compatibility against the preceding
commit and Swift syntax parsing passed. Full regression is running separately
and must not be inferred from these four tests. Syntax parsing is not Swift
compilation. The full Python suite subsequently passed: 349 tests in 200.48s.
Packaged native QA and current-commit CI are still required.

No real Hops retry was made: the earlier live attempt returned HTTP 401 after
successfully reading the configured Keychain credential. Authentic observed
execution still needs binding into the production verification gate. This is
not completed story-to-video or release acceptance, nor a SOP PASS.
