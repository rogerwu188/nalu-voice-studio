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
