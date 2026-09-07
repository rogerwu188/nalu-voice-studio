# Native video decision controls — IN_PROGRESS

The existing video preview now hosts large adoption and return-for-edit controls.
Opening reads the latest local review. Choosing an action prepares a fixed draft
and reads back the meaning through the existing TTS callback; only the final
confirmation posts it. This is not live speech intent confirmation yet.

Requests retain the exact previous-review ID and materialization. A failed or
unverified response keeps the draft for same-intent retry; a separate read-only
record check reconciles state. No provider key or video generation is involved.
Return-for-edit records rejection, not an automatic paid remake. Playback cleanup
also clears the candidate, so a later panel cannot confirm an old preview.

Native URLProtocol/model tests cover no POST on readback, unresolved-intent
preservation, identical semantic retry payload and adopted-state restoration after
restart. Current native CI is required; local toolchain remains blocked as already
documented. Backend video review/progress checks: 13 passed in 4.72 seconds.

Parent 2dec2e0 CI 34088759895 pending and c3405fb CI 34088470406 running at check.
No installed-app visual/accessibility test or real provider video QA performed.
Impeccable hardening guidance preserved native controls, contextual error recovery
and readable confirmation; no redesign or voice-engine changes.

Open: native next-continuous-shot/tail controls, episode assembly/master QA,
actual native validation and controlled release. No SOP promoted to PASS.
