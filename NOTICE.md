# Source and provenance

Nalu Voice Studio productizes the production contracts and tooling from
[`rogerwu188/qingshan-short-drama-production-line`](https://github.com/rogerwu188/qingshan-short-drama-production-line).

The Qingshan engine import is pinned to release `v2026.08.29.1`, commit
`26a8857dbde04dd945cf67e36ca1525639fe8b0d`. This release adds the upstream
MIT license and preserves wardrobe, dialogue-cut safety and pose-transition
contracts at the durable submission boundary.

The upstream repository owner authorized this new open-source productization.
Imported upstream files retain their history-oriented names for traceability;
new runtime APIs and product contracts live outside `vendor/`.

`configs/qingshan-upstream.json` is the reviewed pin and capability-hash
authority. A scheduled audit detects newer upstream releases; upgrades are
quarantined and productized through Nalu contracts and regression QA before the
vendor snapshot changes.

Generated media, credentials, production receipts, canonical project state,
and user biometric material are intentionally excluded from source control.
