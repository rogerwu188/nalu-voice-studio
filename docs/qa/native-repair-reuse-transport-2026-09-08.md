# Native repair reuse transport — incomplete acceptance

## Real encoded preview read at f9cbfff

Unmocked TestClient GETs on isolated `nalu-native-postproduction-qv1poe20`,
child `run_ddfaf60101144e24bf5b2f90b3961549`, returned both existing synthetic
MP4s through repair-scoped content routes. First: 4462 bytes,
SHA256 `f2cc7a1083c17995bc021b6beeedeb0cda4400ba7830276a65c3786eff4c8f50`;
second: 4086 bytes,
SHA256 `4f4f924ffee7eb0865b9964b422bdcc0ed28cb9f478b24df03ed965d904a933e`.
Both matched candidate SHA, MP4 type/ftyp and no-store headers. Wrong candidate
digest returned409 for each. Full child event lists were identical before/after.
No model/provider call or user project operation occurred. This replaces mocked
content-read-only evidence with actual encoded fixture reads, not native playback
or final visual quality acceptance. Child remains an unapproved repair draft.

Added native URLProtocol test for ordinary-run null context and repair context:
only the two expected GETs are issued, no repair creation or production POST.
Backend regression remains 3 passed (5.00s). f6e195b is pushed; latest native
viewer CI34298417543 is pending behind running34297992449. The latter's arm64
job passed, but it predates the viewer and cannot prove viewer acceptance.

Native shot panel now embeds a repair-only viewer after approved shot planning:
GET context/candidates/decisions, explicit clip download, play/pause, user viewing
attestation, and accept/reject. Download does not set the attestation. Leaving
the view stops playback and removes the temporary copy, including late download
completion. Read/save failures retain progress and offer state recovery. This
implements the entry, but native CI and rendered interaction QA are still
required; earlier statements that viewer wiring is absent are superseded.

## Isolated second-shot backend recovery

Using the same qv1poe20 isolated database, the second candidate was explicitly
accepted through the existing review endpoint (HTTP 200, no provider call), and
two newly-created Runtime instances both returned accepts for shots 0 and 1.
This proves durable decision recovery only; it is not evidence that a human
viewed shot 2 in the native UI. Downstream clip-to-edit and final repaired
render remain open.

Review state now separates old CAS receipts from current-plan decisions. A plan
change removes the displayed current approval but retains the prior receipt ID
needed to replace it. New acceptance requires a viewed-shot marker; restoring
a receipt does not manufacture a new viewing event. Added native tests for
these transitions, not yet executed locally (SDK/toolchain mismatch). The UI
must mark viewing only from actual playback interaction, not download success.
CI34298185471 for e017a4d is pending; prior34297992449 remains in progress.

Follow-up: a repair-scoped clip content GET validates the expected candidate
digest and current original-video provenance before serving MP4, with no-store.
Tests cover read-only viewing, stale digest and missing shot rejection using a
mocked media validator; this is not actual playback QA. Native viewer wiring
is still required. f91a065 was pushed; CI34297992449 was pending at inspection.

Native download transport now uses the scoped route with the frozen candidate
digest, checks MP4 response and bounded file size, compares SHA256, and copies
to a private temporary file. The caller must remove that playback copy when
finished. No adoption is performed by downloading. Backend tests: 3 passed in
5.04s; ruff and diff checks passed. Native compilation remains unverified;
CI34297992449 subsequently entered in_progress.

## Native interaction evidence (arm64 artifact, isolated data)

Artifact from CI34298769408 was checksum-verified and launched against the
isolated qv1poe20 SQLite/data root. The app loaded the existing approved-plan
project, opened the shot-plan panel, approved the repair plan, and showed the
repair review panel. Shot 1: `查看原镜头` displayed an MP4 player; `从头播放原
镜头` was invoked; the screenshot showed the pillarboxed video; the viewing
checkbox was checked and `这版使用原镜头` produced the visible receipt
`已确认：这版使用原镜头`. The app then switched to shot 2 through the native
picker and showed its distinct `查看原镜头`/continuity controls. Opening shot 2
loaded the player controls and an unchecked viewing attestation, so a prior shot
approval was not incorrectly reused. No provider call, paid action, or user
project was touched. This is isolated arm64 UI evidence only; Intel/universal,
restart persistence, downstream clip-to-edit, repaired quality, and release
acceptance remain open.

Native transport now reads eligible clips and latest saved per-shot decisions,
and submits an explicit accept/reject with candidate digest and prior decision
ID. Restoring decisions uses GET only; it does not grant paid generation or
master acceptance. Source identity, media hashes and plan identity are required.
Native model tests cover malformed provenance, self-reference and unexpected
production authority. macOS CI must still compile and execute these tests.

Backend repair tests cover latest reject recovery after repository reopening and
unknown-run rejection. Native playback/review UI is NOT implemented by this
checkpoint. Existing historical decisions must not be treated as approval for a
new plan. Actual native interaction and repaired-picture QA remain pending.

No SOP is promoted. The primary source-to-script-to-video objective is unchanged;
this transport supports per-episode repair within that workflow.
