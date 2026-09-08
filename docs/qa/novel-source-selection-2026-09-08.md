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

## Combined and live-source regression at c09c73d

35 tests passed in 6.85s across interactive story, writer service, source reader
and novel import. The opt-in real Wikisource rehearsal also passed again:
100 catalog entries, two chapters saved, second chapter 7,322 characters with
SHA256 `7c17b29129923bad720fd8cc4d66e1892a9ea4a1618f4ae450f498021be23bcc`.
Runtime recreation recovered SQLite and writer request included chapter two.
Evidence database: `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-live-novel-87ddsrqn/nalu.sqlite3`.
No model call and no full-book import occurred.

CI 34265782203 (5fd9b9e source-choice implementation) reports both x86_64 and
arm64 Swift test steps successful; arm64 bundle/smoke/update/rollback steps also
passed. Whole workflow was still running when inspected. Latest c09c73d run
34266276689 was pending, so this is not current-release CI acceptance.

## Persisted source candidates

Story answers now optionally store bounded source candidates and the user's
writing intent in project-owned SQLite. Native project-history loading restores
the last turn's candidates. Once a new turn begins, prior candidates are not
restored as pending. Existing answers without this optional field still decode.
Runtime recreation and idempotent answer replay tested; 15 import tests passed
in 2.60s, ruff passes. Native compile/installed restart QA and OpenAPI snapshot
refresh remain pending. No automatic search or paid retry on restore.
