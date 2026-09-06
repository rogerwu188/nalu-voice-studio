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
