# Writer execution backup and restoration

Status: IN_PROGRESS; packaged backup/native acceptance pending.

Projects with writer execution rows now export v24, a v23 table set plus the
project-scoped writer ledger. Projects without ledger rows retain v23 output.
Restoration uses existing v23 table validation plus strict writer columns,
project identity, allowed state and response digest checks in the same insert
transaction. A changed response is rejected even if the outer export checksum
is recomputed.

Imported execution rows are deliberately quarantined as ambiguous, preserving
response bytes for review. Imported JSON is not authenticated local execution.
Completed, interrupted and timed-out source records all prevent automatic replay
after import. This avoids duplicate calls and fabricated verification; a separate
explicit reconciliation/review workflow remains necessary for unresolved imports.

Four API tests passed across fresh databases: completed/interrupted/timeout
exports preserve records without retransmission; corrupted responses reject the
entire import with no partial project. Ruff passed. No paid calls occurred.
These tests do not establish native backup UI or cross-version app acceptance.
