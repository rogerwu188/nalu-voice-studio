# Qingshan model compiler boundary

Nalu does not treat a model name as a cosmetic setting. Each supported video model
has a separate, versioned local compiler behind the Qingshan adapter:

| Requested model | Compiler adapter | Qingshan profile | Native planning defaults |
| --- | --- | --- | --- |
| `seedance-2.0-pro` | `nalu.qingshan.seedance2-pro` | `SEEDANCE_2_STANDARD_GIGGLE` | 720p, 9:16, 4–15 seconds |
| `MiniMax-H3` | `nalu.qingshan.minimax-h3` | `MINIMAX_H3_GIGGLE` | 768p, 9:16, 3–15 seconds |

The Seedance compiler records its multi-reference image-to-video and exact-first-frame
contract, provider asset/HTTPS reference transports, native-dialogue options, and the
separate upscale requirement for a larger release raster. The H3 compiler records its
omni multimodal contract, exact first/end frames, nine-image limit, public-HTTPS-only
audio/video references, fictional-identity restriction, and separate upscale requirement.
These differences remain machine-readable instead of being hidden in prompt prose.

## Immutable bindings

Every compiler output binds:

- adapter ID and semantic version;
- exact requested provider model and Qingshan profile;
- production-package SHA-256;
- approved-script revision and content SHA-256;
- inherited continuity snapshot ID and resolved-library count;
- inherited asset IDs, kinds, available local SHA-256 values, and transport state;
- provider-specific constraints and planning defaults; and
- a canonical `compilation_sha256` over the whole contract.

The Qingshan workspace manifest stores the compiler-output path and file SHA-256.
Preflight recomputes the production-package digest, compilation digest, package binding,
model binding, and workspace file binding. A stale package, hand-edited compiler output,
model mismatch, unknown model, or attempt to enable paid submission in the local compiler
fails closed.

## Paid boundary

Compilation is not generation authorization. Its state is always
`LOCAL_COMPILED_AWAITING_SHOT_PLAN`, and `paid_submission_enabled` is always false. Shot
planning, prompt validation, provider asset transport, registered Qingshan gates, explicit
cost approval, and the durable transaction submitter remain later mandatory boundaries.
This prevents a successful local dry run from being mistaken for a paid or completed
production.
