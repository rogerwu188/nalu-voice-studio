# Qingshan continuous productization SOP

Qingshan evolves independently. Nalu never tracks its moving `main` branch at
runtime and never copies a release directly into a user-facing execution path.
Every release follows this promotion process.

1. **Detect** — the daily audit compares the latest GitHub release with
   `configs/qingshan-upstream.json` and opens one deduplicated upgrade issue.
2. **Quarantine** — fetch the tag into an isolated checkout; do not modify the
   active vendor snapshot or enable credentials and paid POSTs.
3. **Classify the diff** — record license, dependency, model-policy, submission,
   continuity, QA-gate, schema and historical-path changes.
4. **Map capabilities** — decide which upstream changes become stable Nalu
   contracts, which remain internal implementation details and which are rejected.
5. **Adapt** — update the Qingshan adapter, package/workspace contracts and
   migrations. Never expose E40/E41 filenames or absolute upstream paths.
6. **Verify** — run upstream registry integrity and every registered test before the
   changed-area tests, capability hashes, offline Nalu fixtures, Runtime regression,
   OpenAPI compatibility and full macOS CI. Missing registered evidence is a release
   defect, not a pass that can be replaced by a smaller test subset.
7. **Promote** — update the pinned release, commit, whole-tree digest and critical
   capability hashes in one reviewed change; retain the previous Git commit as
   the rollback point.
8. **Prove** — attach diff summary, test runs and CI links to SOP-07. Paid sandbox
   evidence is separate and always requires explicit authorization.

An upstream release is not a Nalu release. If any gate fails, the current pin
remains authoritative and the candidate stays quarantined.

The current `v2026.08.29.1` pin predates this stronger promotion rule and has eight
missing paths plus one host-specific absolute test path declared by its own gate registry.
The exact exception is commit- and
registry-hash-bound in `configs/qingshan-gate-registry-quarantine.json` and tracked in
[Qingshan issue #20](https://github.com/rogerwu188/qingshan-short-drama-production-line/issues/20).
It may support local contract work, but cannot authorize a paid request. Any added or
changed failure is unreviewed drift and fails closed. The exception must be removed—not
carried forward—when the corrected upstream release is promoted.

The latest reviewed candidate is `v2026.09.04.6` at commit
`3ec9a34a7abad8ae00bfed8cea34706fef4b3fba`. Its tracked-tree SHA-256 is
`5f001db127c365f7aae1921f14e5d1addfc67cd225749c791cf2d87feea63423`; the
registry SHA-256 is
`0b7d478904638f0d9e22452971b7aa8d95b9e7445355b53e364ff187fd0613a4`.
Nalu's isolated audit proves all 69 registered gates are structurally complete and all
66 coded gates are runtime-bound. With credential-like environment variables stripped,
all 33 registered portable modules ran: 210 tests passed with one declared skip, and all
six Writer-v2 tests passed. The candidate still cannot be promoted: its installable
package and CLI declare version `0.3.0`, while the portable manifest declares `0.3.1`.
Between the prior reviewed `.8` tag and `.6`, upstream added a provider-visible per-unit
scope projection, exclusive character-reference ownership, absent-entity prompt scans,
H3 visible-population cardinality and keyframe population evidence. Nalu classifies these
as useful paid-boundary safety semantics to adapt behind its stable contracts; it does not
copy the candidate into the active runtime. `configs/qingshan-candidate-audit.json` binds
the exact public-interface failure,
candidate tree, registry, portable manifest, CLI surface, Writer contract and registered-
test result. CI validates that the record remains `QUARANTINED`, cannot replace the
active pin and cannot authorize paid execution. No provider credential or paid call is
part of this evidence.
Daily discovery treats both the active pin and this exact reviewed candidate as covered;
only a newer, unaudited tag opens a new deduplicated upgrade issue.
Product commit `3000920f78d7e0d2446f0c99eb8264be6c975762` passed all four jobs in
GitHub CI run `33822968508`; Universal artifact `9919040824` has GitHub digest
`sha256:63e2dfe13afc1e5ff84af4ddf86c19a41e2774ab043757f3f454c1322dcaedc8`.
This evidence closes only `.6` discovery and local reproduction, not candidate promotion,
real-provider QA or SOP-07.

Nalu productized two safe `v2026.09.01.7` contracts without copying its runtime into the
paid path: exact adapter/profile/logical/provider model identity at the final I/O boundary,
and local decoded-media EBU R128 release normalization/measurement. Product commit
`76b7283077aedccd8470088f1441c839ba7d6bb7` passed all four jobs in GitHub CI run
`33571104271`; the Universal artifact is `9825078541`. This evidence does not waive the
nine registry defects or the separate authorized real-provider sandbox requirement.

Nalu then productized three safe `v2026.09.02.2` semantics without promoting its source:
entry-state-only scene openings, previous-accepted-final-frame anchors for same-scene
continuations, and locally measured explicit editorial source windows that reject whole
provider-media passthrough. Product commit `872cb3d7aca9d439dbd7045c9474a68be13b7705`
passed all four jobs in GitHub CI run `33685909456`; Universal artifact `9868297261`
has GitHub digest
`sha256:b76f9adae7221cd8e8cb5c4d465903994ed3491abe59171b5ffe91775eb2a9ad`.
The candidate remains quarantined on the same nine registry defects, and no provider
credential, paid task or publication account was used.
