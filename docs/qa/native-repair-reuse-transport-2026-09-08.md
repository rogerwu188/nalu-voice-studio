# Native repair reuse transport — incomplete acceptance

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
