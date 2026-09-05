# Creative intent and production pipeline routing

Nalu's voice entrance is independent from any single media production line.

## Canonical flow

`natural conversation → creative brief → project plan → production route → adapter → deliverables`

The project records two routing fields:

- `creative_format`: `short_drama_series`, `documentary_series`,
  `animation_series`, or `commercial_campaign`.
- `production_pipeline`: `auto` on input, then the selected adapter identifier or
  the explicit fail-closed value `unassigned` in persisted project state.

`configs/production-adapters.json` is the versioned, SHA-256-sealed routing authority.
It declares each adapter's creative formats, required capabilities, supported provider
models, runtime driver and adapter version. Application startup binds those declarations
to the bundled compiler implementations; a version, model-set or driver mismatch stops
startup. Project creation resolves `auto`, while every production start revalidates the
persisted route against the current registry so a quarantined adapter or capability
change cannot silently reach a paid provider.

Each project and atomic project plan also persists a
`nalu.production-route-decision/v1` receipt. The receipt binds the project ID,
creative format, requested pipeline, registry version and registry digest to the
required capabilities, every candidate adapter, its rejection reasons, the selected
adapter, and the resolved pipeline. `decision_sha256` seals the canonical receipt.
Clients can inspect it with `GET /v1/projects/{project_id}/production-route`; an
unreadable, modified, cross-project, or internally inconsistent receipt fails closed.
When the referenced registry is still current, production recomputes and compares the
entire decision before invoking an adapter, then separately revalidates the selected
adapter against the current executable capability registry.

Project export schema v23 carries the sealed receipt so restore preserves the routing
provenance. Older exports remain importable without inventing historical evidence.
For an upgraded legacy project with no receipt, the first production attempt creates a
`legacy_backfill` receipt from its persisted format and explicit pipeline before any
adapter execution; the normal current-registry production checks still apply.

The current UI continues to use the stable Project → Season → Episode storage model,
while presenting audience-appropriate labels:

| Creative format | Group label | Unit label |
| --- | --- | --- |
| Short drama | Season | Episode |
| Documentary | Series | Chapter |
| Animation | Season | Episode |
| Commercial | Campaign | Master/cutdown deliverable |

This compatibility layer preserves the mature multi-episode production contracts.
A later domain migration may introduce generic `deliverable_groups` and
`deliverables`, but it must retain stable IDs and backward-compatible exports.

## Current routes

- Short drama uses `qingshan-short-drama`.
- Animation currently uses the Qingshan adapter with an animation creative profile;
  every project still has to pass the adapter capability and media preflight.
- Commercial projects are captured and planned, but default to `unassigned`.
  Production fails closed until an approved advertising adapter is installed or a
  verified capability profile explicitly promotes Qingshan for that format.
- Documentary projects are captured and planned, but default to `unassigned`.
  Qingshan contributes useful generation, voiceover, layered-audio, selective-BGM,
  subtitle, assembly and QA components, but its pinned contract is still film/short-
  drama oriented. Nalu must not route a documentary to it until a documentary adapter
  adds archive-first editing, source provenance, reconstruction labels, factual review,
  chapter pacing and documentary-specific release evidence.

The application must never relabel a short-drama output as a completed advertisement
when campaign, product-claim, brand-safety, aspect-ratio, duration, or deliverable
requirements were not satisfied.

## Adapter contract

Every production adapter declares:

- adapter ID, semantic version, source provenance, license, and integrity hash;
- supported creative formats, durations, aspect ratios, media inputs, models, and
  required provider credentials;
- brief-to-package compiler and JSON schema;
- local preflight gates and paid-transaction boundary;
- progress, cancellation, recovery, QA evidence, output manifest, and rollback;
- pricing estimator and explicit authorization requirements.

Routing produces the sealed machine-readable decision described above. No adapter
match persists the explicit `unassigned` route and production returns a blocking
error, never a best-effort paid call.

## Voice interview

After audience and guardian setup, Nalu asks whether the user wants a dramatized
memoir, archive-led documentary, animation, or advertisement. Follow-up questions
come from a format-specific brief:

- Drama/animation: premise, characters, world, style, season arc, episode count.
- Documentary: subject, intended audience, chapter arc, confirmed people/timeline,
  available photos/video/audio/handwriting, missing evidence, narrator choice,
  archive-led versus archive-plus-reenactment mode, factual reviewer and desired BGM
  restraint. Generated reenactments must be visibly labeled and cannot silently replace
  a missing historical source.
- Commercial: product, audience, promise, evidence, mandatory claims, prohibited
  claims, brand assets, call to action, channels, master duration, and cutdowns.

The user reviews the plain-language brief before any professional production route
is selected.

## Documentary evidence gate

`GET /v1/projects/{project_id}/documentary-readiness` builds a local, read-only
readiness report from managed assets and their memory cards. Imported material is
reported as `unlinked`, `draft`, or `confirmed`. A confirmed card only becomes
narrative authority when the user also allowed `story_development` or
`visual_generation`; `reference_only` remains useful for follow-up questions but
cannot silently become a factual claim in a chapter.

One confirmed, citable source is enough to begin discussing chapter structure. It is
not enough to enter production. The current report always keeps documentary production
closed while the route is `unassigned`, lists the missing evidence or review steps, and
requires a reconstruction label for archive-plus-reenactment projects. This distinction
prevents an early chapter outline from being mistaken for an authenticated, releasable
documentary.
