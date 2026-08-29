# Runtime API compatibility policy

The `/v1` loopback API is additive. Existing paths, methods, response fields and
schemas may not be removed in place, and an optional field may not become
required. A breaking change requires all of the following:

1. a new versioned path or schema;
2. an append-only SQLite migration;
3. a macOS client migration and rollback path;
4. contract fixtures for both the old and new version during the transition;
5. explicit maintainer review recorded in the pull request.

CI compares the committed `docs/openapi.json` against the target branch (or the
previous main commit on direct pushes). It rejects removed paths, operations,
schemas and fields, as well as newly required request/response fields. Additive
endpoints and optional fields remain compatible.
