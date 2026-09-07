# Native exact-take listening transport — 2026-09-07

Added typed audio listening decision request/receipt and RuntimeClient submission.
Native take receipts now require the saved `take_sha256`, including recovered
attachments. Confirmation binds the sound/edit/cue, asset digest, source offset,
duration and decision; it preserves the expected previous review ID for backend
compare-and-swap. Mismatched input fails before POST. Mismatched responses,
automatic final mix/subtitle/master approvals or non-attestation evidence fail
validation. No provider credential is required for this local action.

Native fixture assertions cover successful acceptance, transmitted prior review
ID and take digest, no POST for a different take, and rejection of altered source
offset, take digest and master approval. Native execution is pending CI because
the local Swift package toolchain remains unusable. No installed UI/listening QA
is claimed; visible controls and decision recovery are the next integration.

Backend workflow regression: `pytest tests/test_image_review.py -q` — 26 passed
in 20.46s, using synthetic media. These are not real family narration or final
master acceptance. No SOP status changed.

Parent 73e11c8024115ae7a0a1d6abf576ea7a2258e60c CI 34100873064 was still running.
Earlier 998d45e0ac74373bee0acc31dcfafc51e56b0ffe CI 34100009067 is fully successful.
