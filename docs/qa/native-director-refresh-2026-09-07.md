# Native save → director refresh

IN_PROGRESS. This source checkpoint is not native UI or real-provider acceptance.

The existing episode editor now saves the user's revision first, then requests
only missing director choices through the version-bound runtime endpoint. Model
credentials come from existing configuration and a noninteractive, off-main-thread
Keychain read. The original local TTS/readback controls remain unchanged.

If enrichment fails, the saved revision remains visible; loading a saved plan
does not trigger another model attempt. An explicit continue action uses the
same source event/hash and the backend's persistent execution ledger. Designed
plans missing director details cannot be confirmed prematurely. Legacy plans
remain readable; no missing detail is replaced with a fabricated QA result.

Impeccable's hardening guidance shaped error messages and input preservation.
The incumbent native controls are reused; no professional form is added.
The save control discloses possible model costs, not video-production authority.

Evidence and limits:

- Added native URLProtocol tests for ordered local-save → refresh, exact source
  route, saved-edit preservation after 502, no refresh on reload, and unavailable
  credentials without new-key prompts. These tests await CI compilation/execution.
- Local `swift test --package-path apps/macos --filter EpisodeShotPlanTests` failed
  before target compilation: installed PackageDescription linker symbol missing.
- Separate Swift frontend parse was also blocked by duplicate SwiftBridging modules.
  Neither command is a passing Swift check.
- Ruff, OpenAPI contract check, product SOP audit and progress audit passed locally.
- The prior `096b478` full CI [34074682613](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34074682613)
  completed successfully, including ARM, Intel and Universal jobs. This does not
  validate the newer native changes.
- Full Python regression: **613 passed, 1 failed in 290.46s**. An abbreviated
  `observed_head` from the previous checkpoint failed its audit test; corrected to
  the full `d2d09d61a5176e0e17a407e38a875a122562855a`, and all six progress tests passed
  on targeted rerun. This is not a claim that the full suite was rerun green.

Remaining: current full regression/CI, compiled native interaction, real provider
acceptance and reviewed-plan → actual per-shot video contract compilation.
No real model, image, video or publication request was made for this checkpoint.
