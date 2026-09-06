# Single-attempt video transport boundary

Status: IN_PROGRESS. No paid calls performed.

The inspected Giggle Seedance skill client specifies x-auth and text/image/omni
generation endpoints, but does not establish server-side idempotent replay.
The existing submitter required such a guarantee. A concrete adapter must not
invent that guarantee to pass the boundary.

Added an explicit opt-in single-attempt transport mode. An atomic local operation
claim precedes an AMBIGUOUS_CHARGE binding persisted before network I/O. Only then
may the one caller dispatch. Task acceptance advances it to SUBMITTED. Process
loss or uncertain response leaves it quarantined; subsequent calls return the
binding without posting again. The quarantine travels with existing remote-task
backup records. Existing provider-idempotent transports keep their recovery path.
An adapter declaring neither capability remains rejected. No HTTP route accepts
an arbitrary transport or enables this mode from user JSON.

45 paid-boundary tests passed, including single-attempt success and SystemExit
after the pre-network record; both make exactly one fake transport call across
replay. These are fixture tests, not paid-provider QA or end-to-end production.
Concrete video payload translation, explicit price approval and remote task
reconciliation remain required.

Previous checkpoint CI 34063554684: ARM64 and Runtime jobs passed, including the
repaired packaged dependency startup and compiled native tests. Intel was still
running when recorded. This does not establish a signed/notarized final release.
