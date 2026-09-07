# Accepted reference image → project-owned asset

Status: IN_PROGRESS. Local runtime registration is implemented; native permission
interaction, automatic design-binding resolution and real provider/video/release
acceptance remain open.

The native-only reference-review registration route requires explicit project-use
confirmation and guardian confirmation for child projects. It revalidates the
latest accepted image review, current confirmed design/package, exact request and
saved image bytes. Shot opening frames cannot masquerade as reference designs.
The existing recoverable importer copies bytes into managed project storage,
records consent and generation provenance, and binds the asset to the source run.
Names, kinds and project scope come from the reviewed design, not a technical form.

Provenance includes source review/design/preparation/materialization/image and
confirmation digests. It explicitly does not claim an authentic historical photo
or professional identity QA. An explicit permission statement is still required;
seeing or accepting an image alone is not permission to reuse it.

An OS file lock serializes registration of the same review across processes.
Committed asset provenance is also the recovery identity if a response or marker
cleanup is interrupted. Replays reuse that asset; changed bytes, confirmation or
revoked permission cannot silently create a replacement. Locks live outside the
managed asset tree so they do not break startup import recovery.

Opening-frame reference use now checks generated-asset registration and latest
source review, as well as existing byte/consent checks. An incomplete registration
or revoked review cannot be reused just because a managed file exists. Automatic
resolution from unresolved design keys to these registered assets is the next
integration; this checkpoint does not claim that integration is finished.

Evidence at writing:

- Targeted registration/import/image-preparation regression: 29 passed in 7.19s.
- Covers synthetic generation receipt, saved image review, registration, repeated
  confirmation, changed bytes/confirmation, revoked permission, child guardian
  requirement and recovery after interruption immediately after the asset commit.
- Final full regression including latest-review rejection and reference-use checks:
  566 passed in 80.13s, two dependency deprecation warnings.
- Ruff, OpenAPI currency/backward compatibility and diff checks passed.
- Prior `968a4fd` CI 34071051850 completed SUCCESS. `f0772a9` CI 34071320708 is
  running (runtime and ARM64 jobs passed, Intel still running); neither is evidence
  for this new registration code, whose CI/native QA remain pending.

No real keys, generation charges, historical identity claims or publication were
used in these tests. Full SOP status remains unchanged.
