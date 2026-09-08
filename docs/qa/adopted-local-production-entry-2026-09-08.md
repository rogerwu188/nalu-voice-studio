# Interactive production entry: remove manual lifecycle fixture bypass

Status: IN_PROGRESS, not project completion.

Verified defect: the native render action submitted to an endpoint requiring
RUNNING, while the interactive adopted-input flow remained WAITING_FOR_APPROVAL.
The former full-render fixture manually updated run/episode states and wrote a
synthetic workspace manifest. Thus earlier rendering success did not prove this
handoff worked for a user.

Implementation: an explicit render request with adopted dialogue now validates
the existing approved edit/audio/captions, immutable package and current approved
script, then checks the exact latest prepared plan. The repository atomically
checks latest run, non-dry-run status, unarchived project, approved revision and
eligible episode state before recording ordinary lifecycle transitions and a
local postproduction start event. No provider dispatch or publication occurs.
The engine writes a real local workspace descriptor without overwriting an
existing descriptor. Origin-bearing browser requests are rejected.

The full-render test no longer edits run/episode statuses or writes its own
workspace manifest. First run passed in 91.84s, producing real encoded synthetic
media and checking QA transition, exact replay and consent revocation. Eight
repository boundary cases passed in 1.60s (changed plan/revision, dry run,
cancelled, archived, wrong episode state, newer run). Thirty-six binding and
immutability regressions passed in 22.47s. Ruff, diff whitespace and backward
OpenAPI compatibility passed. Dependency deprecation warnings remain.

Final rerun passed in 96.25s, including browser-origin and stale-render-plan
negatives before the valid request. Both refusals leave the run waiting for
approval; the valid request enters postproduction and reaches QA without fixture
state edits. CI 34254979644 (older 277a13a) arm64 job passed, but its overall run
was still pending completion; this checkpoint requires its own full CI.

Remaining: current CI and installed native execution, real writer/provider
generation, automatic sound design instead of four manual source requirements,
durable client recovery, user audiovisual review and controlled release. The
synthetic provider/material inputs are still fixtures; their success does not
establish real production authorization or signed/notarized final acceptance.
