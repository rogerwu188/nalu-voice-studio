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

Compiled ARM evidence: CI run 34060675399, commit
c02c8ad748a96371de1c39818637d4221c45b862, completed `swift test`, app build,
release verification, bundle smoke, owner lifetime and upgrade rollback checks
successfully. The overall run is not green: its runtime progress-audit step
failed on an abbreviated commit field, subsequently fixed in e623f12.
Native lost-response interaction remains unverified.
