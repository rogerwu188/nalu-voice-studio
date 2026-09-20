# Shot-plan response recovery

Added the `event_write_failure` case to `test_shot_planning.py`.
The provider transport returns a synthetic valid plan, then draft-event
storage raises an OSError after the writer response has committed.
The test verifies the completed writer response remains durable, recreates
the application against the same database, and recovers the draft with no
second provider call. It continues through revision, explicit approval,
character-card preparation and opening-frame preparation using that result.

Validation: `pytest -q tests/test_shot_planning.py tests/test_writer_execution.py`
completed with 22 passed and two dependency deprecation warnings (13.45s).
No live provider request or charge was made. This is automated fault-injection
coverage, not a real-provider/native end-to-end acceptance or SOP promotion.

Follow-up implementation adds `POST /shot-plans/recover` for a production run.
It accepts a model but no provider credential. No prior attempt returns null;
unresolved attempts reject; completed attempts replay only after exact request
and response digest checks. A local-only transport prohibits any network call,
including if the ledger row disappears. Regression coverage verifies absent,
wrong-model, interrupted-event and failed-provider cases without extra calls.
The same 22 tests passed in 8.56s.

Native read-button wiring now attempts credential-free response recovery after
both the saved-plan read and repair-lineage read return null. The production
view supplies only the configured model name, never the writer key. Recovered
run identity, approval state, authorization absence and digest shape are checked.
An unresolved recovery leaves `loaded=false`, preventing generation fallback.
Two native tests cover successful recovery without credential reads and a409
recovery without generation. Local Swift tests could not start: the installed
CommandLineTools PackageDescription manifest linker reports an undefined
Package initializer. Native CI and installed UI acceptance remain pending;
these tests are not yet claimed as passed.

Hops remains authorized for one shot-plan request up to USD50, with no automatic
retry and no publication. Saved configuration resolves to hopsapi.com/v1 and
gpt-5.4-mini. The current console redirects to email-code login; a verified
model price or enforced account cap is still needed before dispatch.
