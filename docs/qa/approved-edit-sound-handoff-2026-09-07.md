# Approved edit → sound/caption draft — IN_PROGRESS

The sound-plan API now accepts `expected_edit_review_id` with the exact edit ID,
edit SHA and shot-plan SHA. Under the existing SQLite writer transaction it
revalidates the current edit, real source files/adoptions, latest accepted review
and rendered preview receipt. A stale or rejected decision cannot drive an
approved-timing draft, including replay after an intervening rejection.

The result binds the review ID/hash and derives durations from the edited frame
counts, not the original episode estimate. The synthetic two-shot case produces
7 + 6 seconds instead of 15 planned seconds. Caption timing is explicitly
`APPROVED_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT`; this does not approve subtitles,
generate recordings, authorize a voice, accept a master or publish anything.
Unconfirmed edit drafts remain usable for reversible pre-approval planning.

Validation: all 26 `tests/test_image_review.py` cases passed in 21.23s, including
exact replay across reopened Runtime, stale/rejected confirmation rejection,
missing edit identity 422 and all final audio/master flags remaining false.
Scoped Ruff passed and OpenAPI was regenerated. Fixture media and attestations
are synthetic, not paid-provider or human creative QA.

Current native player-controls CI 34095637430 is pending; state-model CI
34094904074 is in progress. No installed UI execution or current complete release
acceptance is claimed. Next connect this approved-timing request to native
post-confirmation orchestration, then obtain actual authorized recordings and
authored sound layers, align captions and pass real master/release QA.
