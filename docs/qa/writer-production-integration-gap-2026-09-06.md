# Writer execution evidence integration gap

Status: IN_PROGRESS — implementation gap, separate from Hops HTTP 401.

Source inspected on ad2f5c3a713118f16aacd32da1e3430fd7d77f74:

- `app.py` defaults to `DisabledWriterProviderVerifier`; packaged startup does
  not install an authenticated provider implementation.
- `writer_provider.py` defines the protocol and disabled implementation only.
- Native `InteractiveStoryWriter.swift` directly sends the generation request
  with `store: false`, then submits the returned raw response for local binding.
- Local receipt reconciliation deliberately reports provider execution false.
  The production engine carries a separate provider reconciliation when present.

Thus a valid key and locally bound draft are not sufficient evidence that the
configured production-verification path is complete. Do not describe the
remaining writer work as exclusively account authorization, nor promote local
fixtures to provider-verified results.

Next implementation must connect authentic execution evidence to the shipped
runtime: either a documented authenticated read-only provider task lookup, or a
runtime-owned durable generation transport which records the actual authenticated
response before the client can claim success. The latter must retain a distinct
evidence type (observed execution, not remote task re-query), persist intent before
I/O, quarantine ambiguous outcomes, and bind request, returned model/task, raw
response, episode script and normalized receipt. Client-supplied JSON alone must
never mint this evidence. Do not turn on provider-side storage of family material
just to make lookup possible without a separate privacy decision.

Continue this concrete integration ahead of additional command-polish work.
Real transport QA remains blocked by recorded Hops 401 until authorization is
resolved; implementation and fake-transport crash/replay tests are unblocked.
