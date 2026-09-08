# Native text and source URL entry

Added a labeled native text field and Send button below existing speech controls.
It binds the existing transcript so the established failure/queue recovery text
remains visible, and submits through commitTranscript rather than a parallel
source executor. Enter and button both use the same typed-submit method. No
default keyboard shortcut is installed globally. Voice-active editing is disabled.

Typed submission rejects blank input, preserves text over 2000 characters with
an actionable message, and ignores stale speech confidence. Added model tests
cover these conditions plus active recording; they await native CI. No local
Swift build or visual verification is claimed due to the SDK mismatch.

Impeccable hardening guidance informed preservation of the incumbent native
controls, meaningful labels and preservation of rejected input. Required installed
QA: keyboard paste/send, actual URL import, narrow window/large type footer
visibility, VoiceOver and recognition-to-typing handoff. No SOP promoted.
