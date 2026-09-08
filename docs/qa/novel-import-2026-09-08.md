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

## Runtime interface

Project-scoped `/v1/projects/{project_id}/novel-import` now supports GET status and
POST selected source/ordered chapters. POST suffixes `fetch-next`, `pause`, `resume`
drive the persisted queue; each fetch performs at most one chapter read. GET
`chapters/{chapter_number}` returns a completed chapter (one-based index), or 409
while incomplete. Status responses omit chapter bodies. Browser Origin writes are
rejected. Selection creation does not perform network work; fetch does not call a model.

14 queue/source/API tests pass in 1.79s, including API-only create/pause/resume/fetch,
app re-creation over SQLite, full-text retrieval and no duplicate completed fetch.
OpenAPI export and backward compatibility pass. Network is still a fixture.
Catalog detection, native orchestration, automatic authorized fetch progression and
writer retrieval remain incomplete. Users must not be asked to fill chapter lists;
the selection DTO is an internal interface for the forthcoming directory parser.

CI 34257181305 for 2892ab807bad75bac4dded7d3bb7d88444315694 fully passed.
This covers the prior native source-routing repair, not this API checkpoint.

## Source-only catalog selection

POST may now omit chapters and supply only source_url. The service validates project
state, reads the directory through the public reader, selects explicit same-host Chinese
chapter-title links, deduplicates URLs and sorts numeric/Chinese chapter numbers.
Duplicate numbering across different URLs fails as ambiguous instead of choosing a volume.
Same-source replay recovers the saved selection without another catalog request.

16 source/import/API tests pass in 1.95s; ruff and OpenAPI compatibility pass. The
source-only API test includes reverse directory order, duplicate URLs, external ads,
navigation and replay. Network is mocked. It is a bounded directory implementation:
paginated catalogs, mixed-volume numbering, source-body cleanup, arbitrary websites,
native invocation and chapter-to-writer context still require work and real QA.
"Complete" queue status only means the selected chapter list was fetched; it must
not be represented to the user as proof that the entire novel was discovered.

## Native explicit-URL entry (awaiting CI/installed QA)

Native action handling now recognizes explicit novel/chapter import plus a URL,
creates/reuses the project, discovers its saved catalog and fetches one chapter per
request with a one-second interval. The existing action status displays stored count.
Project switching stops the next fetch; a completed in-flight fetch can still be saved
to its original project. Import summary is persisted as a conversation answer.
Import does not use the excerpt writer handoff: that would incorrectly write from a
status sentence rather than the imported novel. Chapter-context writer integration
is explicitly still required, not discarded from scope.

Added intent tests for positive import, negation and unrelated protected actions.
`git diff --check` passes. Local Swift toolchain remains broken; tests are not claimed
executed until CI. Still missing: name-only source choice, voice pause/resume, paginated
catalog and clean body extraction, imported chapter writer retrieval and installed QA.

## Bounded source-to-writer handoff

New claimed story inputs now freeze imported source passages into novel_source.
Runtime writer requests include that snapshot; the native Codable model also preserves
it for the configured direct-writer path. This is bounded to 60,000 characters with
exact source URL, chapter digest, character offsets and completeness flags. Explicit
Chinese/Arabic chapter requests select the matching chapter title, not its list index.
It is not whole-novel understanding: large chapters require subsequent passage retrieval,
and global book planning/summaries remain to be implemented. Missing/unread content must
not be claimed read. No real model request was made.

The native import-plus-writing flow now continues an explicit writing request only
when selected chapters finish importing, using the new saved source evidence instead
of a download-status sentence. Native CI/installed verification remains pending.
15 import/story/writer tests pass in 5.53s, including inspecting the actual constructed
writer request and proving later imported chapters cannot change an earlier request
snapshot. A subsequent second-chapter request receives the second chapter. Ruff and
diff checks pass; these mocks are not full website-to-video acceptance.
