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

The latest reviewed candidate is `v2026.09.02.2` at commit
`671dfb09f62fbf0f6f9911bad52a40a5a80cd327`. Relative to the previous reviewed
`v2026.09.01.7` candidate, the release changes 53 files (2,929 insertions and 120
deletions) and adds same-scene chained opening anchors, entry-state-only keyframe
generation, explicit editorial source windows, decoded-frame integrity telemetry and
stronger combat, prop-state, patient-state, camera-authority and cross-episode event
continuity contracts. Nalu reviews those contracts independently without promoting or
running the quarantined candidate. An isolated checkout still fails the upstream
registry-integrity function:
69 gates, 66 coded/runtime-bound gates, eight missing registered paths and one
host-specific absolute test path. The upstream validator can accidentally accept that
absolute path on the machine where the unrelated file exists, so Nalu independently
rejects every absolute registered path before considering promotion.
`configs/qingshan-candidate-audit.json` binds
the exact candidate tree, registry digest and failure list. CI validates that the record
remains `QUARANTINED`, cannot replace the active pin, cannot authorize paid execution
and does not misreport the unrun complete registered suite as passing.
Daily discovery treats both the active pin and this exact reviewed candidate as covered;
only a newer, unaudited tag opens a new deduplicated upgrade issue.

Nalu productized two safe `v2026.09.01.7` contracts without copying its runtime into the
paid path: exact adapter/profile/logical/provider model identity at the final I/O boundary,
and local decoded-media EBU R128 release normalization/measurement. Product commit
`76b7283077aedccd8470088f1441c839ba7d6bb7` passed all four jobs in GitHub CI run
`33571104271`; the Universal artifact is `9825078541`. This evidence does not waive the
nine registry defects or the separate authorized real-provider sandbox requirement.
