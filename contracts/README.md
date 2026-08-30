# Versioned contracts

Contracts are stable interfaces between the Nalu client, local runtime, and
Qingshan adapter. Breaking changes require a new schema version and migration.

- `production-package.schema.json`: immutable input to an episode run.
- `qingshan-model-compilation.schema.json`: provider-specific local compilation bound
  to that immutable package.
- `episode-state-machine.md`: allowed product lifecycle.
- Runtime OpenAPI: generated live at `/openapi.json`.
- `API_COMPATIBILITY.md`: additive `/v1` policy and breaking-change procedure.
