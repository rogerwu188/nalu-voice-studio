# Memory correction and restart regression

Native candidate: `93f962232a22f40c3e172e9b45949d162549e5c2`.
Baseline CI: https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34043029586

The isolated synthetic OCR project was reopened on QA port 18766. Health returned
schema 27. Native UI automation could not proceed: System Events returned
`osascript is not allowed assistive access` (-25211). The isolated application
was terminated by its exact PID. No user project, media, consent, or preferences
were modified. Native correction QA remains IN_PROGRESS, not PASS.

Extended `test_memory_card_requires_explicit_confirmation_and_keeps_evidence`:

- Correct an already confirmed card: revision 3 is a draft, not approved.
- Reopen the runtime using the same SQLite database: confirmed-only results exclude it.
- Confirmation of old revision 2 returns 409 and creates no new confirmation receipt.
- Revisions 1, 2, 3 preserve original OCR and previous place/date values.
- The current record retains its original spoken context.

This is synthetic API regression coverage, not real microphone, human review,
handwriting, or native edit acceptance. No paid service or biometric authorization
was used. The focused regression passed locally. Full local runtime suite:
301 passed (42.68 seconds); Ruff and `git diff --check` passed.

Follow-up: commit `adc21bb35363eb3403342fb83f4d1a5fbfa1f3cc` passed all four
jobs in https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34043937411.
The same regression now exports the corrected project and imports it into a
separate SQLite/data directory. It verifies exact revision/confirmation history,
retained OCR, the corrected date, draft status, exclusion from confirmed-only
results, and rejection of stale revision 2 confirmation after restore. Focused
local regression passed; this remains API coverage, not native backup-picker QA.

Conflict recovery follow-up: the date-conflict regression now corrects the
conflicting year, checks that conflict clearance leaves the card in draft and
outside confirmed-only results, rejects confirmation of its pre-correction
revision without creating a receipt, then explicitly confirms the current
revision. Both original and corrected years remain in revision history.
All five memory conflict tests passed locally; Ruff and diff checks passed.

Packaged runtime follow-up: `scripts/qa-memory-provenance.py` ran against the
previously verified Universal candidate `93f962232a22f40c3e172e9b45949d162549e5c2`.
Real loopback HTTP created synthetic reference-only material, confirmed revision 1,
corrected it to draft revision 2, exported it, stopped the runtime, and restored
into a second isolated SQLite/data directory. Exact OCR, revision history and
old confirmation receipts survived; obsolete confirmation returned 409 and the
restored card remained outside confirmed-only results. Both owned processes
stopped and temporary synthetic stores were removed. No user data was used.
See `packaged-memory-provenance-2026-09-06.json` for runtime binary digest and
bounded results. This script is now included in Universal CI, pending its first run.

CI correction: run 34044862862 failed the progress-file gate because
`observed_head` contained a short SHA. Commit
`3a57c33d3336d83fee9d21a41d2fe1b1930e87e6` repairs the full identity; local audit
passes. The failure was not a passing runtime/native acceptance result.

CI evidence verified: all four jobs passed on
`75adedc5dc38d3d7de63a4391be419b1b118a504`, run
https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34045946711.
Downloaded Universal artifact `9993199632` (GitHub archive digest
`b009433de07cce70fffa49465c478d9208eb32a320c00f91e19835c937b1b663`).
The inner ZIP digest was independently computed and matched its manifest:
`35f0ccca5680f6587e14b353cd91c38bfd0e67b6c6c1be09d6a27c687b542b37`.
The packaged `nalu-memory-provenance-universal.json` reports PASS; its runtime
digest `ea02d56ae0a09041268a30b4c2ed40dd102b543a5378cb5e5e99f5c5515b9cd9`
matches the locally extracted binary. These are bounded packaged-runtime results,
not native UI, human voice, Developer ID, notarization or whole-product acceptance.

Extended local rehearsal on the downloaded `75adedc` runtime also passed:
`packaged-memory-conflict-2026-09-06.json`. The synthetic narrative cards with
different event years block confirmation. Correcting the year clears the conflict
but leaves a draft; the previous revision is rejected, no receipt is created for
it, and only explicit confirmation of the corrected revision archives the card.
Reference-only material is deliberately exempt from narrative conflict blocking;
the fixture explicitly permits its entirely synthetic text for story-development
QA before asserting that boundary. No biometric permission was granted.
