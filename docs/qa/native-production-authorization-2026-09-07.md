# Native conversational production authorization

IN_PROGRESS, not native acceptance or completed production.

The approved episode shot-plan panel now has a large **确认本集制作预算**
action using the existing native visual language and local speech playback.
The user says a budget, hears it read back with the credits/currency and local
estimate caveats, then explicitly confirms it. No technical form, model key,
default budget or paid call is introduced by this action.

The client reads the same run and library-snapshot preview, checks the selected
project/episode and displayed approved-plan ID/hash, and refuses stale library
context. A confirmed request is sent only to the new production-authorization
endpoint; its response must echo the exact approval and run. The existing plan
refresh mechanism preserves unsaved edits. Subsequent per-task cost approval and
dispatch remain separate and unfinished in the native workflow.

Budget collection cannot itself approve anything. Child mode requires the exact
guardian confirmation phrase. Negative responses cannot become approval. Ordinary
unrelated questions return to the normal assistant; budget context remains.
Cancellation stops the pending conversation, not existing server authority. A
failed save retains the identical submitted request for an explicit retry.
Switching projects clears pending local input. Unsubmitted budget drafts are
in-memory; after restart they must be restated, not silently considered approved.
Already-authorized runs are read from the runtime on re-entry.

## Verification

- Native tests added for Chinese/Arabic budget parsing, ambiguity/decimal rejection,
  separate readback, revised amounts, negative/off-topic statements, guardian
  confirmation, cancellation, identical retry, and exact authorization receipts
  without provider/writer key headers or dispatch calls.
- `swift test --package-path apps/macos --filter ProductionAuthorizationTests`
  failed before source compilation: local CommandLineTools PackageDescription
  manifest linker missing `Package.__allocating_init`. These tests have **not**
  passed locally; current macOS CI must run them.
- Backend regression: production authorization, library refresh, image budget and
  goal progress audit: **31 passed in 10.16s**. `git diff --check` passed.
- Prior native video-preparation commit `040a149` full CI
  [34081854943](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34081854943)
  succeeded. Backend authorization `7dc24bb` CI was still running at this check.
- Current source has not been built/installed or visually verified in a native
  app. Desktop inventory was readable, but it is not QA evidence for these changes.

Remaining: current native compilation/tests and UI acceptance; per-image/video
cost confirmation/dispatch; real source-to-script-to-episode-master and release
acceptance. No SOP is promoted to PASS. Impeccable hardening guidance kept the
incumbent large controls and focused this change on context, confirmation and
failure preservation rather than visual redesign or voice polish.
