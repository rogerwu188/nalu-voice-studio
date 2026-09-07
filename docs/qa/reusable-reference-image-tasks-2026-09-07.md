# Confirmed visual designs → reusable image tasks

Status: IN_PROGRESS. This implements runtime production dependencies, not live
generation, registered project assets or full video/release acceptance.

Selecting a confirmed shot in the existing native path now prepares unresolved
character, scene and prop reference tasks before its opening-frame task. A shared
design key has one `REF-<key>-design` task per run, reused across shots and after
restart. Existing references are not regenerated. Task records bind the exact
current approved plan, script package, project style, design and request digest.
Invalid/stale opening shots are checked before dependency creation.

The request is concrete and uses the existing bounded image transport: one image,
character/prop references at square 1K and scene references at the documented
matching-ratio project resolution. Descriptions remain source-bound creative
designs, not claims of authentic historical photos or likeness authorization.
Reference preparations deliberately have no `approved_shot_index`; native frame
selection cannot mistake them for an opening frame. Opening preparations retain
their unresolved reference dependency task keys.

These preparations reuse the image estimate envelope, durable submit/observation,
download/materialization and exact-image review services. A reviewed reference is
not automatically registered as a project asset or deemed professional identity
QA. The production submit route is still not enabled without real pricing and
the concrete authority/contract path.

Evidence:

- Initial related regression: 53 passed in 15.19s.
- New reference suite: 8 passed in 2.71s, including two-shot dependency reuse,
  restart, budget binding, stale/cancelled/unknown/wrong-task/style rejection,
  and synthetic submit → query → materialize → accept → restart replay.
- The transport/authority/receipt/image in that lifecycle test are synthetic;
  no real credential, generation charge or user identity was used.
- Ruff, OpenAPI currency and diff whitespace checks passed.
- Full Python regression: 560 passed in 77.85s, two dependency deprecation warnings.
  OpenAPI is backward compatible with the preceding commit. This commit's CI and
  native QA remain pending.
- Prior candidate `968a4fd`: CI 34071051850 ARM64 job succeeded; runtime and Intel
  jobs were still in progress. This is not evidence for the new dependency code.

Next: bind accepted reference images to project-scoped assets with explicit
provenance/permissions, then resolve those bindings into the confirmed shot's
opening-frame inputs without rewriting the approved plan or resubmitting a paid
reference. Complete real authority/pricing and provider execution, video, QA,
masters and controlled release. The original narrated/online-source writing
workflow and local TTS priority remain unchanged.
