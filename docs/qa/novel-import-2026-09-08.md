# Web novel import — incomplete

Requested journey: find the novel source, collect accessible chapters in order,
persist on this Mac with resumable state, and supply the imported content to the
interactive episode writer. No copyright questionnaire gate is requested. Login,
paywall and network access restrictions are not bypassed.

## Complete-page reader

`read_public_chapter` reuses the existing public-IP-pinned HTTPS transport and
redirect validation. It reads the complete bounded page text plus document-order
link candidates, title and next-link rel metadata. It does not claim every link
is a chapter or that document order is the final novel order. Chapter selection
and website-specific content extraction remain required.

The existing single-page excerpt API remains unchanged at 24,000 characters.
The new reader fails above the existing 1 MB response bound rather than silently
importing an excerpt. Script execution and credential forwarding are not added.

Tests: `pytest -q tests/test_source_reader.py` — 10 passed in 1.14s, with two
dependency deprecation warnings. Transport is mocked: evidence covers long-page
retention, explicit oversize failure, link ordering/deduplication and existing
source security/endpoint behavior, not a real novel website. Targeted ruff passes.

Still missing: catalog/source discovery integration, chapter/body selection,
durable SQLite jobs/chapters, progress/cancel/resume, native voice import action,
writer retrieval of imported chapters and real-site/installed QA. Do not mark
novel import or SOP-04 complete from these tests.

## SQLite import queue

NovelImport now stores selected ordered URLs, chapter text/digests, resolved URLs,
progress and attempts in the existing project's SQLite bible namespace. It follows
that namespace's project lifecycle; large imports currently rewrite the JSON value,
so dedicated chapter storage/pagination is a performance follow-up, not a scalability
claim. Limits are explicit: 2,000 selected chapters and 20 million stored characters.

Each fetch claims one pending chapter transactionally, releases the database lock
during network access, then compares its attempt token before committing. Completed
chapters are retained across service recreation. Failures require resume, not implicit
retry; pause/recovery invalidates in-flight responses. No new request starts paused.
A hard crash remains fetching until explicit recovery; native recovery is not wired yet.

13 source/queue tests pass in 1.48s, including restart, retry, successful-chapter dedupe,
selection mismatch, pause during fetch and crash recovery. First run exposed a fixture
whose text was exactly 24,000 characters, fixed to test beyond that boundary. Ruff passes.
Network remains mocked. No API/native caller, automatic catalog selection, writer context
retrieval or actual novel import is claimed complete.
