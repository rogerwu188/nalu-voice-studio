# Interactive plan → professional video contract: remaining implementation gap

Status: IN_PROGRESS. This is source-level diagnosis, not a completed compiler or
provider/native QA. Current code inspected at `46525d2` on 2026-09-07.

The remaining core path is not blocked only on credentials or prices:

- `shot_planning.py::ShotDraft` contains a single `camera` string. The paid
  boundary requires ten explicit director fields: scale, height, side, axis,
  motion family/direction, start/end framing, motivation and lens intent, plus
  provenance preserving those exact choices.
- Its `entry_state`/`exit_state` prose and transition flag do not compile into
  explicit state-delta dimensions, intentional-hold reason or first-scene
  prior-episode event relation and authored continuation action.
- `visual_asset_keys` identifies designs, but neither counts visible living
  entities nor creates the complete package-bound identity/reference projection.
- Props lack per-shot owner/hand/position/disposition endpoints and a separate
  exact-frame visual confirmation. A review button or generated design must not
  automatically manufacture the professional visual PASS.
- `tasks_for_plan` produces timing and dependency identifiers, not these
  contracts. `VideoPreparationService.validate` immediately calls the full paid
  validator, so an ordinary interactive shot cannot currently cross this gap.
- The native `EpisodeShot` Codable model would discard newly introduced fields
  unless extended alongside the backend; edits/restart must preserve them.

## Next executable implementation sequence

1. Extend AI director drafts with typed camera, state-delta, prop and continuity
   choices sourced from the confirmed script/design catalogue. Preserve unknown
   facts and distinguish creative proposal from historical or visual verification.
2. Round-trip these fields in native review and present a short plain-language
   readback with existing TTS. Users correct meaning, not JSON or professional
   forms. Bind later edits to a new reviewed version; do not retain stale authority.
3. Compile the confirmed choices, actual registered references and actual accepted
   frame into the exact request consumed by the existing full validator. Source
   any identity/visual QA from separate evidence, never hard-coded PASS or empty
   populations when a person is in the shot.
4. Exercise both narration and web-source projects through this same handoff,
   including multiple episodes and continuous shots. Then complete real priced
   production, postproduction QA/master and controlled release.

This unblocked implementation takes priority while applicable image rates, Hops
account authorization and native Mac unlock await external state. Keep the
reference-price/native-spending work open; do not substitute another generic
callback, more mocked receipts or voice polish for the missing director compiler.
