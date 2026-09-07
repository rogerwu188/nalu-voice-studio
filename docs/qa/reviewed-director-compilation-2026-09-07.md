# Reviewed director choices → video preparation

Status: IN_PROGRESS. Creative compilation is implemented; a complete real video
request and the user-facing end-to-end journey are not yet accepted.

`VideoPreparationService._plan_binding` now derives missing camera/authority,
state-delta, combat classification, prop endpoints and first-scene relationship
fields from the exact current approved shot. Explicit conflicting values are
rejected rather than replacing the reviewed choices. The compiler fills a copy
before updating the request, so conflicts cannot leave a partly compiled request.

Camera choices become LOCKED to the reviewed values with a canonical digest.
Intentional-hold reasons and prop-transition descriptions are retained. Independent
prop-frame confirmation is preserved if present, never invented. UNKNOWN prior
episode relationships remain UNKNOWN and fail the professional boundary until
properly resolved. No character-count, frame, price or payment proof is fabricated.

Evidence:

- Compiler + shot planning + paid-boundary tests: **106 passed in 49.40s** before
  the final two pipeline-binding assertions were added.
- Final compiler + shot-planning rerun: **21 passed in 15.94s**, including actual
  approved-plan binding, automatic field population and rejection of changed camera.
  Initial failures in these new assertions were test import-scope errors, fixed.
- Ruff and OpenAPI checks passed. No real model/provider/publication call made.

Remaining production work: bind visual design keys to authoritative project
characters and actual approved assets; derive the complete visible/absent character
scope without dropping people, including handling counts incompatible with the
current one-instance-per-character provider contract; attach real accepted frame
bytes/evidence; expose native per-shot preparation and complete pricing/dispatch.
The current immutable run package can predate generated character designs, so an
empty original character catalog must not be misrepresented as a zero-person shot.
Resolve that source/catalog lifecycle explicitly before real production.

Current candidate CI/native acceptance remain pending; no SOP is promoted to PASS.
