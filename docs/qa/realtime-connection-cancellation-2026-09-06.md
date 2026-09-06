# Realtime connection cancellation

SOP-02 stays IN_PROGRESS.

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
script with simulated media/transport: **6 tests pass** locally, covering Stop at
five async boundaries and an old microphone result after a replacement connection.
Mocks deliberately ignore abort to exercise late-result rejection. No browser
microphone, key, network or provider is used. The test is added to runtime CI;
full new CI and actual WKWebView/package cancellation QA remain open.
