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
