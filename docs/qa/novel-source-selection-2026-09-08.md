# Native novel source selection — IN_PROGRESS

Explicit novel-import searches without a URL now present up to five returned
sources and wait for an explicit numbered choice. Selecting a source invokes
the existing URL import path and preserves an accompanying script-writing request.
No source is selected automatically. Switching projects clears the pending choice;
negated, quoted, out-of-range and publication-bearing choices do not match.

Added native unit coverage; execution awaits CI (local CLT is incompatible).
Prior product commit d7c6d76 fully passed CI 34264614852. This change has not yet
passed native CI or installed speech QA. Pending selection is currently in-memory,
so restart requires repeating source search; durable recovery remains open.
Search results are candidates, not verified catalogs. Catalog failure preserves
the project. No paid model/search request was executed for this change.

## Natural wording follow-up

The first selection implementation only recognized explicit download/import verbs.
Expanded novel import intent to include novel-to-script requests, including
“找一本小说，拿来写剧本”, so search summaries do not substitute for chapter text.
Article-only requests remain on the article path; negation, search-only and
publication commands remain excluded. Added native routing and selected-query
handoff tests. Backend novel-import regression suite: 12 passed in 2.33s.
These backend tests do not execute the native wording change; native CI and
installed conversation acceptance remain pending. No SOP status is promoted.

## Bounded long-chapter continuation

Runtime now recognizes explicit “继续改编小说下一段” (also reading/processing)
and continues after the previous frozen passage offset. The persisted story
context carries a hash-bound cursor without duplicating passage text. Exhaustion
does not wrap to chapter one; pending chapters block traversal rather than being
silently skipped. Ordinary script revisions do not advance this cursor.
13 import tests pass in 2.15s; ruff passes. Full-book planning, natural paraphrase
coverage, paid writer execution and installed E2E remain unaccepted.

## SQLite restart and revision continuity

Recreated Runtime/repository over the same SQLite after the first 60,000-character
window. Next input reaches the remaining 100 characters; replaying its turn ID
produces the identical writer request. Found and fixed ordinary revision input
resetting the source window to chapter one: revisions now preserve the frozen
window/cursor. A subsequent continuation reaches an empty new-material window,
without wrapping. 14 import tests pass in 2.47s; ruff passes. Model requests are
constructed only, not sent. No native speech or final script-quality claim.
