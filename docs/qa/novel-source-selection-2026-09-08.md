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
