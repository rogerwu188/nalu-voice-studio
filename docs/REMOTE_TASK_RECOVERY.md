# Durable remote task recovery

Nalu records a paid remote-task intent in local SQLite before any provider request may
leave the Mac. The record is bound to the production run, task key, provider, requested
model, submission fingerprint and exact request SHA-256. Reusing a task key with changed
generation inputs fails closed.

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

This is a persistence and recovery boundary, not a provider submission feature. The
current Qingshan gate-registry quarantine keeps all paid execution disabled. Before paid
production can be enabled, the imported durable submitter must be the only caller of this
contract and authorized sandbox QA must prove prepare/request/response/ledger crash
boundaries against the real provider.
