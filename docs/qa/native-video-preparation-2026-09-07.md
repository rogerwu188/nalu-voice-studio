# Native accepted-frame video preparation and public-price preview

Status: IN_PROGRESS; not dispatched video, native QA or full project acceptance.

The existing frame review now offers “下一步：准备这个镜头的视频” after explicit
acceptance of an exact opening frame. Shared reference cards cannot use it.
The client rereads the approved plan and requires its ID/digest to match the
frame decision, then sends only shot index, plan hash and frame-review ID to
the reviewed-video endpoint. Returned preparation must match run, plan, shot,
review and materialization; paid/generation flags must both remain false.

Prepared video evidence is recovered from run events on reload without another
video-preparation request. The bound image can no longer be changed from that
panel. On preparation failure, accepted image bytes and review remain available.
The native event decoder now supports video preparation while retaining its
existing tolerance for unrelated event types.

A separate large “查看这个镜头的预计费用” button reads public pricing through the
existing local backend. It checks exact preparation/hash, observation type,
expiry and non-generation flags. The text/TTS explains that public credits are
an estimate, not a provider-enforced charge limit. A failed lookup clears stale
price state but preserves the video preparation. No key lookup, reservation,
paid submission or publication is performed by these actions.

Impeccable hardening guidance influenced preservation/retry states and existing
native control reuse. The UI does not add professional forms or change the local
TTS baseline. The parent shot view now passes its readback callback to the frame
panel, so action explanations use the same existing TTS path.

Evidence:

- Native tests added for accepted-frame GET/POST handoff, no credential lookup,
  exact route, saved-event recovery without repeat preparation, failed preparation
  retaining the accepted image, bound quote display and clearing failed quotes.
- 31 related backend/frame/price/progress tests passed in 10.87s; Ruff/diff passed.
- Native tests are pending current macOS CI. Installed local Swift tooling was
  verified broken before source compilation in the preceding native checkpoint;
  do not report these new tests as locally executed or passing.
- Prior 97b0d62 full CI 34080974999 succeeded. Backend cb1c10d CI 34081413828
  was in progress when inspected.
- No actual UI capture, current native interaction QA, provider call or live
  pricing lookup was performed by this development checkpoint.

Remaining: explicit cost approval/guardian policy, budget reservation and protected
dispatch UI; real generation and receipt reconciliation; continuous tail-frame
lineage, prop evidence, additional model transports, full episode/master/release
acceptance. A public-price preview is not spending authorization.
