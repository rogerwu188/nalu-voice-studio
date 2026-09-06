# Runtime writer observation in production packages

Status: IN_PROGRESS, following `d10d77ebe25d0d9fd731ec893e1f656a68f777b1`.

New production packages include an optional `runtime_writer_observation`, separate
from authenticated remote-task reconciliation. Runtime reads only completed
execution rows in the same project, validates raw response integrity and identity,
reconstructs the per-episode receipt, and requires its exact hash to match the
script-bound receipt. The record carries the script revision, receipt record hash,
response hash and invocation request hash, without exporting the raw conversation.
Ambiguous/imported executions produce no observation. No network call is made
by this binding operation. It does not authorize production or claim remote lookup.

MockTransport integration covers generation, artifact reconciliation, explicit
script approval and a local dry-run package containing the observation. Ten
observation/story/provider tests passed; additional mismatch and corruption
assertions also passed in a subsequent targeted run. Existing remote
reconciliation remains distinct. Ruff and OpenAPI compatibility passed.

The preceding native endpoint checkpoint passed all 349 Python tests in 200.48s.
That full-suite result predates this observation addition. This addition still
requires full CI, native packaged QA and actual provider acceptance. The fixture
is not a live Hops success or produced video. Downstream consumption of the new
observation and the actual per-episode production demonstration remain open.
