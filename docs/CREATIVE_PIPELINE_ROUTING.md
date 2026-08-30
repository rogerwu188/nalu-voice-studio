# Creative intent and production pipeline routing

Nalu's voice entrance is independent from any single media production line.

## Canonical flow

`natural conversation → creative brief → project plan → production route → adapter → deliverables`

The project records two versioned routing fields:

- `creative_format`: `short_drama_series`, `documentary_series`,
  `animation_series`, or `commercial_campaign`.
- `production_pipeline`: the selected adapter identifier.

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

Routing produces a machine-readable decision with the requested capabilities,
candidate adapters, selected adapter, rejected reasons, and policy version. No
adapter match means `blocked`, not a best-effort paid call.

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
