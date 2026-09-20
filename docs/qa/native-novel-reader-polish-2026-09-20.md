# Native imported-novel reader and extraction follow-up

## Installed UI observation

Candidate `79b823088f84df3b5ce9341f01b88b9d8423bfd0` was launched from the
arm64 CI artifact in an isolated local-QA support directory and bound to the
100-chapter public Wikisource import. The accessibility tree exposed the saved
chapter controls and the full chapter body. Selecting chapter 2 changed the
visible title from `第一回` to `第二回` and loaded distinct saved text. No model
endpoint was available to that app and no content was refetched by UI navigation.

This revealed that MediaWiki header/download chrome was included in the saved
reading text. The follow-up implementation adds MediaWiki-specific structural
filtering, prefers the page's accessible chapter link title over an arrow glyph,
and removes the known page footer controls. It does not claim universal
clean-text extraction for arbitrary sites.

## Verification

- `tests/test_source_reader.py` and `tests/test_novel_import.py`: 45 passed.
- `ruff check` on changed Python files: passed.
- Unmocked HTTPS re-read of Wikisource chapters 1 and 2 returned the expected
  literary body; download label, page navigation, sister-project panel, top
  link, and category controls were absent. Chapter bodies: 6,985 and 7,079
  characters respectively.
- Existing source import rows were not mutated; this extraction change applies
  to new reads. The currently installed UI artifact is the previous candidate,
  so the cleaned body is not yet native-artifact verified.
- CI 35537739655 for parent `79b8230` succeeded on runtime, arm64, x86_64, and
  universal jobs. The new extraction changes require their own complete CI.

## Boundary

This is a source-reading improvement only. It does not verify AI screenplay
quality, video production, final human acceptance, distribution, signing or
notarization. Project SOP remains incomplete.
