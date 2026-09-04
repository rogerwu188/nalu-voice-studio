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
- paid-boundary requirements for duration, explicit combat classification, honest native
  delivery resolution and the prohibition on silent upscale; and
- a canonical `compilation_sha256` over the whole contract.

The Qingshan workspace manifest stores the compiler-output path and file SHA-256.
Preflight recomputes the production-package digest, compilation digest, package binding,
model binding, and workspace file binding. A stale package, hand-edited compiler output,
model mismatch, unknown model, or attempt to enable paid submission in the local compiler
fails closed.

The committed Draft 2020-12 JSON Schema is an executable closed contract for compiler
version `1.7.0`, not a descriptive subset. It enumerates every provider and paid-boundary
field, couples model, adapter, profile, native limits and provider contract, and rejects
unknown properties. CI validates generated Seedance and H3 compilations, independently
recomputes their compilation digest, removes every paid-boundary field one at a time, and
injects unknown paid/provider fields to prove both omission and unreviewed expansion fail.

## Paid boundary

Compilation is not generation authorization. Its state is always
`LOCAL_COMPILED_AWAITING_SHOT_PLAN`, and `paid_submission_enabled` is always false. Shot
planning, prompt validation, provider asset transport, registered Qingshan gates, explicit
cost approval, and the durable transaction submitter remain later mandatory boundaries.
This prevents a successful local dry run from being mistaken for a paid or completed
production.

The durable submitter revalidates the same contract immediately before its only allowed
provider write. Every grouped request must preserve a finite model-supported
`duration_seconds`, an explicit combat/noncombat classification, the compiler's native
and delivery resolution, an honest native-resolution label and
`silent_upscale_forbidden: true`. A combat choreography contract cannot be combined with
an explicit noncombat declaration. Conversely, words such as “禁止战斗” in a negative
prompt do not silently turn an explicitly noncombat scene into combat. Missing,
conflicting, out-of-range, non-finite or resolution-drifted values fail before the
transport is called.

The version `1.7.0` compiler contract also requires a Nalu-owned
`nalu.qingshan-provider-scope/v1` projection for every paid shot. The projection lists
only the shot's visible character and prop IDs, requires exactly one visible instance
per character, binds each reference index to one exclusive visible identity, and fixes
background and unbound living-entity counts at zero. Episode characters absent from the
shot are represented only as local forbidden-term checks; the episode-global story graph
is explicitly unavailable to the provider. MiniMax H3 scans the complete rendered prompt,
including negative clauses, and requires explicit `@ImageN` identity/cardinality plus an
exclusive population clause. Seedance preserves its separate negative-prompt semantics
and scans only positive provider content. Any missing, duplicated or contradictory scope
fails before the durable submitter can call a transport.

The projection is not trusted as its own authority. At the sole durable paid boundary it
must carry the exact approved production-package SHA-256 and a canonical digest of the
package's complete character-ID catalog. The submitter reloads and rehashes the immutable
package, independently derives every confirmed character from `resolved_library`, and
requires the disjoint union of visible and absent IDs to equal that catalog exactly.
Under-declaring a character, relinking a projection to another package, overlapping the
visible and absent sets, duplicating package identities, or changing either digest fails
before intent persistence and before provider I/O.

Each materialized workspace also contains the result of Qingshan's own gate-registry
integrity checker. A known upstream release defect may be quarantined only by exact
upstream commit, registry SHA-256 and failure list. A quarantine can keep local compilation
usable for offline product work, but `paid_execution_allowed` remains false; any new drift
fails preflight.
