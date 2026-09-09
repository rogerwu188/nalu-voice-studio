# Native repair reuse transport — incomplete acceptance

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
