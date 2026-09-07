# Native transcript persistence — 2026-09-07

Typed native submission maps timed recording drafts to the Runtime transcript
contract. Save responses and recovery validate take/review, source audio hash,
sample count, recognizer identity, segment bounds and explicitly unapproved flags.
Save additionally compares returned text/segments to the submitted draft.

The recording model now saves after recognition. A failed save retains the draft
and offers a separate retry method; it cannot start a fresh recognition over that
unsaved draft. Recovery reads a saved record without repeating ASR. Changes to the
recording acceptance clear the old transcript receipt. Visible buttons still need
to call these methods; no installed UI or live-ASR acceptance is claimed.

Native test source covers exact submitted digests, saved/read/null records and
rejection of an old review. Tests await native CI. Backend accepted recording /
transcript fixture passed: 1 passed, 25 deselected in 26.08s. Ruff/diff checks passed.
CI 34103363309 for 842f683c4c9160935c436a7bda5aded97fca8366 is fully successful.

Remaining: visible start/retry/recovery and draft review; ASR cancellation/timeout;
current native CI and real recognition QA; confirmed subtitle timing and final
mix/master/release. No SOP status upgraded.
