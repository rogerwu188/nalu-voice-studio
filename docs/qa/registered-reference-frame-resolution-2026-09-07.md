# Registered reference assets → concrete opening-frame inputs

Status: IN_PROGRESS. Runtime resolution is implemented and covered by synthetic
integration tests. Native compilation/interaction and real generation remain open.

Opening-frame compilation now resolves each previously unresolved design against
project assets by exact source run, approved plan, design key and design digest.
It refuses ambiguous matches and incompatible kind/scope, and revalidates the
registration, latest accepted review, original materialization, current permission
and managed bytes. Existing snapshot-bound supplied materials keep their original
validation path. All references share the provider count/byte limits.

The resulting request includes actual base64 image bytes in ordered image-to-image
references and records their asset IDs/digests. The saved plan and production
package are not rewritten. Missing designs remain explicitly unresolved; a single
registered character does not count as a complete scene-reference set. Repeated
shots reuse the same character, and completed reference dependencies are not
prepared again. Updated request digests do not authorize another paid submission
or silently update a spending reservation.

Native frame loading now always asks runtime to refresh local preparation before
matching an existing generated frame. It cannot reuse an old matching-plan record
when newly registered references changed that record's actual request. The action
remains local/idempotent and never sends provider credentials or a generation POST.
Impeccable hardening informed this stale-state fix; existing layout, controls and
local TTS were preserved rather than redesigned.

Evidence:

- Related Python integration: 49 passed in 13.13s, two dependency warnings.
- Exercises image registration → exact bytes in two separate shot requests,
  unchanged approved plan, stable local preparation ID, unresolved scene tracking,
  and rejection after permission revocation or file modification.
- Swift URLProtocol tests updated for local refresh; a new stale-request test
  verifies old frame bytes never become reviewable. Compilation/native QA pending.
- Ruff, OpenAPI currency and diff checks passed. Full Python regression:
  566 passed in 77.86s, two dependency deprecation warnings.
- Previous CI: f0772a9 / 34071320708 completed SUCCESS; 876142a / 34071632998
  running at final observation. These are not this change's CI evidence.

Next: native reference-image review/permission/registration orchestration, complete
real image pricing and QingShan authority, then real sequential video, master QA
and controlled release. Neither synthetic reference bytes nor one green test run
establish a working real story-to-release workflow.
