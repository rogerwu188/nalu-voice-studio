# Native accepted-frame video generation panel

IN_PROGRESS; no real generation/payment or native visual acceptance claimed.

## Connected path

The accepted-frame panel now hosts `VideoGenerationPanel` for the same immutable
video preparation. It first reads saved video reservations and observes any
submission locally. It does not submit from load, reload or price review.

For a fresh task the user views the price, selects **确认费用并生成这个镜头**,
hears the exact price and already-authorized run budget, then explicitly confirms
in the native dialog. Child mode propagates to this opening-frame panel and the
final button explicitly identifies guardian approval. No new form or voice engine.

The model checks the current paid-approval run and quoted preparation/expiry,
saves the exact reservation, reads any existing submission again, and only then
reads the existing Keychain key and calls explicit dispatch. If a competing request
has already submitted, it only shows that saved result. Changed reservation task
or request identity is rejected before dispatch.

On a lost result the reservation is retained, automatic retry is disabled, and
**核对提交状态** reads saved state without provider I/O. Restart recovers from
run events. If an approved reservation has no submission binding, the user may
explicitly continue that same reservation; the backend revalidates current context,
price and single-attempt authority. Expired quotes do not silently get replaced.
Submitted, completed, ambiguous-charge, cancelled and zero-charge-failed states are
distinguished without claiming that a completed provider task is an accepted master.

## Verification

- Added native model tests: load/review only GET; explicit confirmation produces
  reserve/observe/submit; second confirmation does not post again; lost dispatch
  response survives fresh model creation using GET only; dry run and unreadable
  history do not read keys or dispatch.
- Local `swift test --package-path apps/macos --filter VideoGenerationTests` again
  failed before source compilation on the CommandLineTools PackageDescription
  manifest link. New tests require current macOS CI; no local pass is claimed.
- Backend regression: **97 passed in 20.51s**, covering paid submitter boundary,
  video pricing and progress audit. `git diff --check` passed.
- Prior native cost bridge `04049bf` full CI
  [34083790655](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34083790655)
  and conversational authorization `340c440` full CI
  [34083297991](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34083297991)
  succeeded. These do not validate the current panel.

## Remaining

Current native build/tests and installed-app QA are required. Voice-only final
per-shot confirmation remains to be connected; this checkpoint uses existing TTS
readback and an explicit native button. Provider polling, retrieved video review,
tail-frame lineage, sequential generation, full episode postproduction/master and
controlled release must still pass real E2E acceptance. Image price and Hops access
blockers remain as recorded in GOAL_PROGRESS. No SOP becomes PASS.

Impeccable guidance preserved incumbent large controls/local TTS and focused the
change on context, consent and error recovery, not visual redesign.
