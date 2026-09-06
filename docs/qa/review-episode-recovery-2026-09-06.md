# Episode creation response recovery

Status: IN_PROGRESS. Swift parse and whitespace checks passed; compiled tests
and native interrupted-adoption QA pending.

Interactive draft adoption now resolves the intended episode by season ID and
episode number. Existing episodes retain their title and plan. If the create
request fails after committing, the client performs a read-only reconciliation
and continues with the persisted episode. It never repeats the create POST in
that recovery path. Cancellation is respected; a record from another season
cannot satisfy recovery.

`ReviewEpisodeRecoveryTests` uses a transport fixture to simulate a lost create
response, unchanged existing plans, and cross-season rejection. These tests are
not evidence of full native script approval or production. The season-create
step, script revision and receipt reconciliation still form separate steps;
the whole adoption workflow is not an atomic server transaction.
