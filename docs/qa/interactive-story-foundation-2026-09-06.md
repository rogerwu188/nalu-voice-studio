# Interactive writing checkpoint — IN_PROGRESS

User priority: narrated story and online source inputs must lead to interactive
episode writing, then confirmed production and controlled release. Existing TTS
is the baseline. This checkpoint is not that completed workflow.

Implemented:

- SQLite project-owned conversation, revision checks and payload-bound turn IDs.
- Restart recovery, retained drafts on lookup/writer failure, stale-answer rejection.
- Native runtime client and project-bound saving of research requests/results.
- Late research results do not appear in a newly selected project.
- Existing projects do not get the idle "create new project" resume instruction.

Local evidence: full runtime suite **315 passed** (including two new interactive
story regressions); Ruff and Swift parse passed.
Added two Swift regression tests; compiled execution belongs to CI, not parse.
CI results and native QA remain pending; no SOP is promoted.

Still missing: actual interactive AI writer integration, source retrieval capability
verification against configured service, source selection/rights handling, automatic
draft display and honest AI-provenance handoff into script revisions. Real native
two-path QA and production/release demonstration remain open. No paid request,
generated video or release is claimed by these synthetic tests.

API request documentation inspected for the next writer step:
[Chat Completions](https://developers.openai.com/api/reference/typescript/resources/chat/subresources/completions/methods/create).
This documentation does not establish third-party provider compatibility.

## Native writer integration follow-up

Ordinary story input now calls the configured service's `chat/completions` with
the configured text/research model and project-owned history (including saved
lookup answers). It creates a project when none is selected, produces unapproved
episode drafts in the conversation, persists the answer and speaks the short
reply using existing TTS. No production, approval or publication is performed.
Calls have no automatic retry. In-flight inputs remain durable after a crash;
they are not automatically resubmitted.

Three Swift tests cover configured Hops host/model, accumulated source context,
concrete script decoding and invalid/truncated answers. Local Swift parse passed;
compiled tests and real service compatibility remain pending. Schema-constrained
output is validated locally; a provider rejecting JSON mode must not be silently
treated as success or rerouted to another host.

Still open: genuine writer receipt/provenance capture and script-revision handoff,
native draft review/restart display, source content acquisition and source rights,
multi-season numbering, in-flight follow-up handling, and both real end-to-end
user journeys. Draft conversation output alone is not a completed writing flow.

## Draft adoption implementation (pending compiled/native QA)

The client now captures the actual returned model/task identifier, request/rules/
response digests and the raw response body (not authentication headers). These
remain unverified client declarations, not proof of provider execution. SQLite
retains them with each answer, and tracks the writer of the current episode draft.
A new correction does not inherit the old draft's writer declaration.

An explicit `采用第1集草稿` command creates/selects the season and episode and
submits the draft as `external_ai_generated` into the existing script-review API.
It does not approve the script or start production. A matching content/receipt
revision is reused on ordinary retry; concurrent-client atomic idempotency is
not yet established. Multiple seasons without an identified current season are
not silently guessed. Source episode numbering still needs full season binding.

Local: full runtime suite **316 passed**, including three interactive tests;
Ruff/Swift parse/OpenAPI compatibility pass. Added Swift declaration and
explicit-adoption parser tests. Compiled CI for this change, native adoption and
provider receipt reconciliation remain pending. Prior writer candidate `def710d`
has arm64 and runtime success in CI `34057559900`; Intel was still running at
20:22 UTC. That result does not validate this later adoption change.

## Regression and restoration follow-up

CI `34057785241` arm64 failed compiling `38ec1b1`: `NaluEpisode` lacked
`seasonID`. Added decoding of the existing runtime `season_id` field, with a
regression test. This candidate is not native-QA ready until new CI compiles it.

Project switching/restart now restores persisted turns and script drafts to the
conversation; pending calls are shown as unresolved and are not resubmitted.
First-use web lookup now creates a project and saves its query/results there.
Compound lookup-plus-download/publish requests execute only the read-only lookup
stage, leaving the protected action unexecuted. Real source retrieval and native
journey QA are still open. Added restoration tests; local Swift parse passed.

## Supplied URL reading

Implemented a project-bound public HTTPS text reader and connected supplied URLs
to it in ordinary conversation. It pins a validated public IP while keeping TLS
hostname verification, rejects private/reserved DNS answers and credentials,
checks each redirect, accepts only text/HTML and bounds the response/excerpt.
No account login, paywall bypass, paid service or publication is involved.
Returned text is labeled as one-page excerpt, not a complete novel or granted
adaptation rights. Native conversation retains up to 8,000 characters with source
URL; later writing uses the saved source context.

Real read-only check: user-provided QingShan GitHub repository URL returned
17,233 extracted characters, `truncated=false`, `single_page_excerpt`, repository
name present. This proves public page reading, not novel acquisition or adaptation.
Full local runtime suite **319 passed**; Swift parse, Ruff and OpenAPI compatibility
passed. Compiled CI for source reader pending. Prior candidate `14b4ed1` has both
Swift test jobs passing in `34057920337`, arm64 artifact `9996575318` available;
its remaining jobs were still running. Named-book search service compatibility,
multi-page import/rights confirmation and real native two-path QA remain open.
In-flight spoken follow-ups are still a known gap; do not mark them complete.
