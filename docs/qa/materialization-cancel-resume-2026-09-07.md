# Materialization cancellation and explicit resume

Parent: `af6adb5a0f536413b2b478f916ef6851b3e943c0`.
Scope: real local media encoding with synthetic fixtures, HTTP cancel/resume and
SQLite run events; not a real provider generation or installed native user QA.

The previous cancellation fixture only stopped at the first probe, before any
encoding. It now checks three deterministic interruption points:

1. Before work: cancellation returns 409; no completed output or success event.
2. After an actual normalized segment has encoded: partial staging is cleaned;
   cancellation stays authoritative; explicit resume produces one QA-review result.
3. After durable output promotion, before state advancement: the complete files
   are retained, the cancelled run does not gain a success event, and explicit
   resume verifies/reuses those bytes without calling the encoder again.

All cases assert one cancellation event, no premature materialized event,
abandoned-stage cleanup, and exactly one materialized event after resume.
Existing committed files are byte-identical after the third case's recovery.

The third case initially failed its error-message assertion: the throttled
250 ms decode probe could miss a just-arrived cancellation, then the repository
correctly refused state advancement with a generic status error. An uncached
final run-state read now returns the explicit cancellation error. The repository
transaction remains the authority against a later race; this is not a claim of
atomic external publication or rollback of already incurred provider costs.

Targeted tests: 3 passed, 25 deselected in 7.18s. Ruff passed. Full regression and
current CI verification follow; no SOP is promoted by this checkpoint.
Follow-up: complete rendered-output immutability plus live dialogue consent
regressions passed, 36 tests in 22.55s. Current CI is still unverified.

Next: connect native adopted-dialogue staging and production actions, with
automatic sound preparation/selection rather than exposing professional path,
hash or timing forms to elderly users. Native QA, semantic/master QA, paid
provider validation and signed/notarized release acceptance remain open.
