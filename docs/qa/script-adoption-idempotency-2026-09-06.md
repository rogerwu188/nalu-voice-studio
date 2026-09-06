# Atomic script revision retry protection

Status: IN_PROGRESS; bounded backend/native integration checkpoint.

The native adoption flow previously used a list-then-create check, which cannot
prevent simultaneous clients from creating duplicate revisions. It now supplies
a stable receipt-derived retry key. The runtime inserts the key, request digest,
revision and episode transition in one SQLite transaction. A matching replay
returns its original revision; changed content under the same key conflicts.
Keys are scoped to the episode, so other episodes cannot consume that result.

Replay lookup precedes the current episode transition check: replaying an old
successful request after another version is approved must return the old result
without changing approval or reopening review. Requests without a key still
represent intentional new versions. Project deletion removes these retry rows.

Tests cover four concurrent submissions yielding exactly one revision, restart
replay, conflicting content, separate episodes, intentional new version and
preservation of later approval. API additions are optional/backward compatible;
Swift parsing is not a substitute for compiled/native QA.

This does not make the entire season/episode creation plus receipt reconciliation
one atomic transaction. Season selection and that broader recovery path remain
open. No video generation, provider verification or publication is implied.

Local evidence: 328 runtime tests passed; the targeted test additionally verifies
retry-record cleanup on synthetic project deletion. Ruff, Swift parse, exported
OpenAPI freshness and compatibility checks passed. CI/native adoption evidence
for this change is still pending.
