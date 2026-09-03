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

The latest reviewed candidate is `v2026.09.03.4` at commit
`856870f1aa97452b85b229a118566b37219f2683`. Relative to the previous reviewed
`v2026.09.03.3` candidate, the release changes 16 files (921 insertions and four
deletions), restores all eight registered evidence paths and makes the portable CI invoke
the registry gate. Nalu's independent no-execution audit now proves all 69 registered
gates are structurally complete and all 66 coded gates are runtime-bound. The candidate
still cannot be promoted: its installable package and CLI declare version `0.3.0`, while
`configs/PORTABLE_CORE_MANIFEST.json` declares `0.3.1`. Nalu records that exact public
release-contract drift separately from registry integrity, keeps the source quarantined
and does not run its registered suite or authorize a paid call.
`configs/qingshan-candidate-audit.json` binds
the exact candidate tree, registry digest and failure list. CI validates that the record
remains `QUARANTINED`, cannot replace the active pin, cannot authorize paid execution,
requires its public interface to remain portable and does not misreport the unrun
complete registered suite as passing.
Daily discovery treats both the active pin and this exact reviewed candidate as covered;
only a newer, unaudited tag opens a new deduplicated upgrade issue.
Product commit `0fe4cf18f2edc79b007be1970fecf99092d91590` passed all four jobs in
GitHub CI run `33788826554`; Universal artifact `9906713225` has GitHub digest
`sha256:ac7bfccd624c6405a23977f1ef399eb14e433179370e0846e162d426e65722fa`.
This evidence closes only the public-interface audit checkpoint, not candidate promotion
or SOP-07.
Commit `562c602b9ffb06b3f222195b9bac45c5ab0dd6b4` then bound all six public CLI
commands and the four repository-owned render/submit/release entry points. GitHub CI run
`33790673885` passed all four jobs; Universal artifact `9907427075` has digest
`sha256:0d66ea1c90551f4ccacff5dbaf64cb9b66a1dffa96e8163498b0fee8aff32b4f`.
Nalu keeps its stronger paid-transaction and decoded-media controls instead of adopting
the upstream fallback as authority.
Commit `8ece75411457076c5e0602516351560fb811c189` independently records the `.4`
registry closure, the remaining `0.3.0`/`0.3.1` public-version conflict and Writer v2
provenance contract. All four jobs passed in GitHub CI run `33792752813`; Universal
artifact `9908224100` has digest
`sha256:2ffbbe0835e61ba017a54c970c1beb63f1bbd5edbb4009c86e05820b279c1bb7`.
Upstream portable-core CI run `33791985563` also passed, but it did not detect the
cross-manifest version conflict and therefore is not promotion evidence.

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
