# Visible transcript workflow — 2026-09-07

The existing recording review area now offers local transcript generation,
save-only retry, saved-draft recovery, read-aloud and cancellation. It displays
unapproved draft text and optional relative word timings. Opening the area reads
existing saved transcripts but never starts recognition automatically.

Transcript work owns a cancellable task; disappearing cancels it and suppresses
late spoken status. Buttons follow the model's approved-recording/busy/pending
guards. An uncertain save cannot be replaced by new recognition, and recovery
cannot treat a different old draft as the pending draft's successful save.

Impeccable hardening guidance was used to preserve existing native large buttons,
wrapping text, explicit progress/errors and pending user work. No professional
form, new visual design or voice-engine change was added.

Added native availability assertions for absent/accepted/historical acceptance.
Native execution and actual screenshots, keyboard/VoiceOver and live permission/
recognition QA remain pending due to the recorded local toolchain issue. Backend
accepted-audio/transcript fixture: 1 passed, 25 deselected, 17.08s. Ruff/diff passed.
CI 34104369487 had ARM passing while Intel/Runtime remained running when checked.

Still required: explicit subtitle corrections/confirmation and final sound/master/
release. This visible source wiring does not complete SOP-04 or the full project.
