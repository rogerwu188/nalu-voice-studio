# First authorized live video

User selected option 1: a storybook opens and a miniature village rises from its
pages. Submitted once through the installed Seedance skill's text-to-video client,
using the existing environment credential. No publication.

- Model: seedance-2.0-pro; 5 seconds; 16:9; 720p; count 1.
- Campaign: giggle-live-test-2026-09-20; aggregate allowance 10,000 credits.
- Reservation: 130 credits based on freshly fetched public 26 credits/sec rate.
- Task: 807de96b-f261-4ebc-9c73-ef14f47d8fd9.
- Terminal query: completed; result https://gigg.cc/377un5.
- Query response SHA-256: 71bc34ca01a3cda6c52eac39c2f463e35b48796beab602876fbef9aeeff4183f.
- Exact task-ID-filtered statement read observed SingleGenerateVideo Pay: 100 credits.
  This is an observed charge, not a reconciled full campaign balance. Preserve
  the 130-credit reservation conservatively; 9,870 credits remain unreserved.
- Private durable database: ~/Library/Application Support/NaluLiveTests/campaign.sqlite.
- Resume: scripts/run-giggle-storybook-test.py queries the saved task. It cannot
  submit again after the dispatch claim, even if acceptance recording fails.

Live API returned `running`, previously rejected by the runtime query parser.
Normalize it to `processing`; all 12 task-query tests pass including that case.
No failed query triggered another generation POST.

The video has NOT been visually/aurally accepted, imported into an episode,
signed, notarized or released. A provider result is not full SOP acceptance.

Attempted native in-app browser preview of the exact returned URL. Browser
reported `net::ERR_BLOCKED_BY_CLIENT`; no frames or audio were observed. Do not
record this as playback or quality acceptance, and do not download media to
bypass that display restriction. CI 35534653123 for 2624bbf was pending at this
inspection, not passed.

## Import boundary inspection

`AssetService.import_bytes` already accepts `generation_provenance` and optional
episode scope. Import requires actual media bytes. The production-video
materialization endpoint instead requires an existing run observation and an
exact matching provider-task binding. This standalone campaign has no approved
episode shot binding, so it must not be inserted as that run's generated shot.
No binding was fabricated and no import or review was performed.

Separately verified CI 35533755125 (7721e44, native approval snapshot guards):
runtime, arm64, x86_64 and universal all succeeded. This is older than the live
campaign implementation and is not evidence for its latest CI. Current local
`tests/test_story_to_review_journey.py`: 3 passed, two dependency deprecation
warnings, 4.95 seconds; fixture-backed story/review flow, not paid writer E2E.
