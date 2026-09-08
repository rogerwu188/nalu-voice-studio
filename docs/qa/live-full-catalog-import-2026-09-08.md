# Real 100-chapter catalog import

Executed `scripts/verify_live_novel_import.py --chapters 100` against
https://zh.wikisource.org/wiki/西遊記 through public runtime endpoints. Exit 0.
The opt-in script retains the default two-chapter smoke run and adds a bounded
2..100 argument, 0.5-second pacing and progress every ten chapters.

All 100 discovered chapters reached complete. A separate SQLite connection then
verified every chapter's stored UTF-8 SHA256 against its body: 100 verified,
741732 total characters. Ordered newline-joined chapter hashes digest:
`84737963032aa819a8ba3f77a87f934da5fa2f61b7b60751651a86ff0ff8017c`.

Isolated database:
`/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-live-novel-v_vxcy42/nalu.sqlite3`.
The script also verifies pause/restart/resume and chapter-two binding in a writer
request. Second chapter digest:
`7c17b29129923bad720fd8cc4d66e1892a9ea4a1618f4ae450f498021be23bcc`.

This proves complete import of this discovered catalog, not a critical-edition
textual completeness comparison, all website compatibility or entire-book model
comprehension. No model called; no user project touched. Native UI journey,
real writer generation, video and publication acceptance remain outstanding.

Follow-up on the same saved database: `verify_source_windows` traverses the full
explicit 1..100 range with the production 60000-character context budget. Thirteen
windows concatenate exactly to all741732 stored characters, with no skips or
duplicates. Joined text SHA256:
`f5b5cbcc383297efbaf1f8c4d178600431e3fecefc8faa24b77c730324603494`.
The reusable helper was executed directly against the saved state and is now
part of future `--chapters 100` runs. No new download or model call was needed.
This verifies source traversal, not model understanding or narrative continuity.
