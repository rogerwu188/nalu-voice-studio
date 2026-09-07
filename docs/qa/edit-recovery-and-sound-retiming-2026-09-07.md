# Saved edit recovery and sound retiming — IN_PROGRESS

Native episode loading now reads saved edit events after obtaining current staged
inputs. A fresh model restores the latest same-plan edit only when source identity,
ordered shot inventory, ranges and frame-rounded duration agree. Unrelated event
payloads are ignored, foreign runs and malformed/stale matching edits reject.
No saved edit is overwritten by recovery. Existing in-memory changes survive
reload; a history read failure leaves the initial state unset so retry can recover.
No provider generation or keys are involved. Native test additions cover actual
GET-only history recovery, no edit resubmission, source mismatch and wrong duration.
Those tests await macOS CI; local Swift manifest linker remains unavailable.

Sound-plan API optionally accepts a paired exact edit ID/hash. It revalidates the
latest edit, approved plan, script and actual adopted media, then derives cue and
caption-draft timing from the edited frame counts. Planned and edited duration
remain separate. The timing basis explicitly says draft edit windows, not speech
alignment; no edit/voice/caption approval or recorded audio is fabricated.

26 image-review workflow tests passed in 11.86s, including actual two-shot media:
edited sound cues are [0,7] and [7,13] instead of [0,8] and [8,15]. Replay returns
the same sound draft; wrong edit hash rejects, and an unpaired edit ID rejects.
Ruff services/tests/scripts passed and OpenAPI regenerated. Current native CI,
installed app recovery QA, preview/explicit edit approval, native retiming action,
recordings and complete real postproduction/release remain required.

Previous goal turn classified as progress: b5f101c changed committed native code.
Its CI 34092064555 remains pending; 9802db8 CI 34091496570 has ARM/runtime success
but Intel still running. Neither observation supports full product completion.
