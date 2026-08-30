# Durable remote task recovery

Nalu records a paid remote-task intent in local SQLite before any provider request may
leave the Mac. The record is bound to the production run, task key, provider, requested
model, submission fingerprint and exact request SHA-256. Reusing a task key with changed
generation inputs fails closed.

`DurableRemoteTaskSubmitter` is bound exactly once when the Runtime starts. The repository
has no public prepare/transition mutation methods; its internal mutations require the
unforgeable, per-Repository authority held by that one submitter. The production service
and application state reference the same instance. A second binding, a fabricated
authority, or an alternate Runtime source that invokes `post_paid_task` fails automated
regression checks.

Immediately before its paid transport boundary, the submitter reopens the immutable
production package and verifies its canonical SHA-256, explicit paid-generation approval,
approver identity and requested model. It then requires a transport that declares provider
idempotency support. The package hash, run, task key, provider, model and request hash form
the provider idempotency key; a changed request cannot reuse the durable task identity.

The durable state machine is:

`prepared → submitted → completed`

with explicit side paths:

- `prepared/submitted → ambiguous_charge` when a timeout or response cannot prove whether
  the provider charged or created a task;
- `prepared/ambiguous_charge → zero_charge_failed` only after an exact zero-credit receipt
  proves a retry can be considered separately; and
- eligible nonterminal states may be cancelled with provider evidence.

`submitted` and `completed` require an immutable provider task ID. Once bound, that ID
cannot be changed or silently discarded. `completed` additionally requires a result URI,
receipt and reconciled nonnegative credit total. Provider task IDs are globally unique in
the local database, preventing two production units from claiming the same remote task.

Each state update and its ordered run event share one `BEGIN IMMEDIATE` SQLite
transaction. A crash after the binding row changes but before the event is written rolls
back both. On restart, Nalu can recover the exact state and provider evidence; replaying
the same evidence is idempotent, while changed evidence is rejected.

The episode progress view derives plain-language stages from these records. In
particular, an ambiguous response is shown as “正在核对是否扣费”, disables cancellation,
and states that Nalu will not submit again automatically. A verified zero-charge failure
is distinct from an ambiguous charge and still waits for renewed approval before retry.

An offline provider double proves the highest-risk local crash window: the provider
accepts the task, the Runtime crashes before response evidence commits, and restart sends
the identical idempotency key. The double returns the same task ID and records one charge.
Timeout-with-unknown-charge is instead persisted as `ambiguous_charge`; replay reads that
state without invoking the transport again. These tests make no network call and are not
evidence about a real provider's idempotency or ledger behavior.

The current Qingshan gate-registry quarantine keeps all concrete paid transports
unregistered and paid execution disabled. Before paid production can be enabled,
authorized sandbox QA must prove prepare/request/response/ledger crash boundaries and
ambiguous-charge reconciliation against each real provider.
