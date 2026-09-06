# Durable writer invocation foundation

Status: IN_PROGRESS, not enabled for client generation yet.

SQLite migration 28 adds project/turn-scoped execution records, with foreign-key
cascade deletion. The runtime-only `WriterExecution` operation commits a
`submitting` record before invoking an injected transport. Destination and request
bytes bind the attempt identity; changed requests conflict. Successful raw JSON
responses are retained with a digest and replayed locally. Concurrent, interrupted
or ambiguous attempts cannot automatically invoke the transport again. Exceptions
are not stored, to avoid persisting credentials in transport error messages.

Three transport-fixture tests verify commit-before-I/O, completed replay across
executor reconstruction, request/destination conflict, timeout quarantine and
concurrent suppression. They use no external service. Ruff passed.
The full local suite passed: 332 tests. Packaged migration and CI are pending.

This module does not assert provider verification: a JSON object is not enough
to prove a valid model response. Trusted HTTP transport, response/task/model
validation, native wiring, episode receipt binding, backup/privacy handling and
authenticated observed-execution provenance must be implemented before enabling
the path. No client endpoint accepts response JSON to create these records.
The existing native generation path is unchanged in this checkpoint.
