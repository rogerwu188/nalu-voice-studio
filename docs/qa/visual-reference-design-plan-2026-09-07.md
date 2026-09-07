# Script → reusable visual-reference design plan

Status: IN_PROGRESS — source-bound planning and native review wiring, not image generation.

New AI shot-plan requests now require a shared `visual_assets` catalogue of
character, scene and necessary prop designs. Each design has a plain-language
name/description, an exact script excerpt and a plan-local key. Shots reuse these
keys. `existing_asset_id` may name only a real inherited asset of the same kind;
otherwise it is null. Draft keys are never registered as existing photo IDs.
Instructions require unspecified appearance, clothing and factual details to be
marked for confirmation, not invented as established autobiography facts.

Validation checks unique keys, literal source excerpts, known same-kind links,
exact linkage to each shot's selected existing references, one scene design per
shot, no repeated/unknown references and no unused designs. Task records identify
which designs still need creation. This is structural/source validation, **not**
proof that an AI found every person/prop or correctly understood the whole story.
Semantic and actual visual QA remain necessary.

The native plan model preserves the catalogue through edits and decoding. The
selected shot displays its human-readable material plan and includes it in the
existing local read-aloud action, explicitly labelling designs as not generated
images and not permissions. Impeccable hardening guidance kept existing native
type/layout and protected old-plan decoding; no professional input form was added.

Confirmed-shot image preparations carry the relevant reference designs and an
explicit unresolved-key list, without faking uploaded/generated reference bytes.
Existing image consent and pixel checks still apply to linked assets. Legacy
saved plans remain readable; an edit of a newer plan may not silently strip its
catalogue. New provider responses without the catalogue are refused. Updating
the model request does not authorize retrying an earlier durable invocation.

Initial targeted tests: 37 passed in 5.24s, plus Ruff and OpenAPI compatibility.
Final full Python regression: 552 passed, two dependency deprecation warnings,
in 107.70s. Ruff, OpenAPI currency and `git diff --check` also passed.
Coverage includes unknown/wrong-kind references, missing/duplicate scenes,
duplicate/unused design keys, source mismatch, shared designs, local review and
preparation linkage. Swift round-trip/readback tests were added but need this
commit's CI; native screenshot/interaction QA remains pending.

Separate preceding-candidate evidence: CI 34070488317 on `c09fd75` passed Swift
tests on ARM64 and x86_64; the full workflow subsequently completed SUCCESS. That supports
the earlier automatic-preparation implementation, not this new catalogue UI.

Next: convert confirmed unresolved designs into project-scoped reference-image
preparations and actual verified generation, then enforce complete QingShan
identity/scene/entry-state contracts. Applicable image pricing, paid submission,
actual frames/video/postproduction and controlled release are still incomplete.
