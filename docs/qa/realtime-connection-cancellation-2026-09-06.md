# Realtime connection cancellation

SOP-02 stays IN_PROGRESS.

Broker/coordinator commit `c13082ae512eeb94f82eed0bce27a55bd7d7fa6c`
passed [full CI 34055471880](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34055471880)
on 2026-09-06: Runtime, both macOS architectures and Universal package gates.
That run predates the browser guard and native WebKit test commits below.

The [official WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)
documents client-secret creation followed by a separate SDP call exchange. In
Nalu, an attempt gate previously discarded a stale returned token, but the broker
could still POST for that token after a delayed Keychain read, even if the user
had already stopped connecting. Discarding the response did not prevent that
external request.

The coordinator now owns the token-request task, cancels it on Stop and before
replacement, and forwards caller cancellation. The broker checks cancellation
before credential lookup, after it returns, before transport and after response.
A late system read cannot trigger the cancelled request. A request already sent
before cancellation cannot be retroactively unsent; transport cancellation and
the existing attempt gate still protect subsequent local activation. No automatic
retry or provider capability assumption is added.

Injected synthetic-credential tests cover broker cancellation before a late read
returns and coordinator Stop retaining the off state after that return. A custom
URLProtocol fails if any request reaches transport; WKWebView loads local HTML
only, with no token available to begin audio. No actual keys, microphones or
provider calls are used. Local syntax/diff checks pass; compiled CI, packaged
cancellation QA and real authorized Realtime acceptance remain pending.

## Browser handshake continuation

Inspection also found that the embedded page continued after getUserMedia,
createOffer, local SDP, fetch and response text without checking which connection
owned the result. Stop now increments a connection generation and aborts an active
handshake; each async boundary checks ownership. Late microphone tracks are
stopped, and old peer/data-channel callbacks cannot affect a replacement session.
The response of an already-sent request may still exist remotely; this is not a
claim to undo an external effect.

`node --test tests/realtime-webrtc-cancellation.test.mjs` executes the embedded
script with simulated media/transport: **10 tests pass** locally, covering Stop at
five async boundaries and a late result at each boundary after a replacement connection.
Mocks deliberately ignore abort to exercise late-result rejection. No browser
microphone, key, network or provider is used. The test is added to runtime CI;
full new CI and actual WKWebView/package cancellation QA remain open.

`RealtimeWebKitCancellationTests` now loads the unchanged production HTML in an
ephemeral WKWebView, injecting synthetic media/peer/fetch before document load.
It covers the same ten Stop/replacement boundary combinations in WebKit rather
than Node VM. A bounded stage deadline fails instead of hanging if setup breaks.
Syntax validation passes locally; execution is pending the next macOS CI build.
This deliberately does not exercise native microphone permission or provider
transport, so it is not real Realtime acceptance or installed-app manual QA.

## Candidate deb9cc0 verification

[CI 34055936631](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34055936631)
is running on `deb9cc01b4b54bb891ee73eadcf18258aae3a1e8`. Both arm64 and x86_64
Swift test steps have succeeded, as has the ten-case Node test step. Full jobs,
Universal packaging and individual WebKit test log inspection are still pending.
The same clean local source passed all **312 Runtime tests** in 45.26 seconds;
two existing dependency deprecation warnings remain. None of these simulated
checks closes the real voice or signed release acceptance gates.

### Native arm64 package follow-up

Artifact `9995982902` from that run was downloaded; ZIP SHA-256:
`0c71cbd76a667ba399937bdee99aad9e83ff2f0f42c8cb61396513a17ea2b6d4`.
App process `90994` and bundled runtime `91008` were launched from
`/tmp/nalu-cancel.3RK4CU/app/Nalu Voice Studio.app` on the existing isolated
`tmp.gEDfvkaLEc` QA data at port 18769, after stopping the precisely identified
older QA processes. No production data was used or removed.

System Events readback on the first credential-sheet open reported all three
stored-key badges and `https://hopsapi.com/v1` in the non-secret address field.
Secure fields were not read or changed. Escape dismissed the sheet. No microphone,
client-secret request or generation was initiated. This is startup/settings
retention evidence, not a packaged real voice cancellation test.

The arm64 job log explicitly reports the WebKit ten-scenario test passed in
9.197 seconds and 139 Swift tests with zero failures; broker cancellation tests
also explicitly passed. Both architecture jobs and Runtime are now successful;
Universal remains live at this observation.

Final CI observation: run `34055936631` completed successfully, including Universal.
The x86_64 job log also explicitly reports the WebKit scenario passed (1.783s),
with 139 Swift tests and zero failures.

On process 90994 a single saved-key model diagnostic was requested. Seven seconds
later the UI reported Keychain read timeout, explicitly no provider connection,
and an enabled Check button. Thus provider access remains blocked before HTTP;
stored presence does not prove key readability. User action must occur locally
in the Keychain prompt or Nalu's secure draft field, never by sharing the secret
in chat. No real Realtime call was attempted.
