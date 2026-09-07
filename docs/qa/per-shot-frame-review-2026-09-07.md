# Per-shot frame decisions during sequential production

Status: IN_PROGRESS; backend production handoff repair, not real video acceptance.

Previously any video preparation, budget reservation or remote binding in a run
blocked all new frame reviews for that run. That prevents reviewing the next
independent shot once an earlier shot enters production.

Entry frames now protect their corresponding video task. Task identity comes
from the validated ImagePreparationRequest and its exact `-entry` image key,
not a name suffix alone. Shared reference images remain protected across the
whole run; legacy preparation records without a task identity still fail closed.
The same-shot lock applies regardless of the remote task's completion state.
Already-recorded identical frame decisions remain replayable.

VideoPreparationService now holds the same SQLite writer lock during validation
and event insertion. Image review/library refresh cannot commit between reading
their evidence and the video preparation record that protects it. Identical
preparations deduplicate within that transaction; no provider call occurs.

Evidence:

- `tests/test_image_review.py`: current frame review succeeds with another shot's
  preparation/reservation/remote binding, rejects each same-shot variant, still
  rejects stale/tampered images, changed plans and unknown legacy downstream work.
  These use synthetic provider responses and a local image, not paid production.
- `tests/test_reviewed_frame_entry.py`: injected validation attempts a second
  SQLite writer and verifies it cannot change the package before preparation
  commits; replay creates one event. This lock test is not full contract validation.
- Related image-review, entry, concrete transport and progress tests, including
  the final exact entry-type guard: 37 passed in 8.05s.
- Ruff/diff checks passed. Native 0f8c536 CI 34080624095 still running when inspected;
  preceding c2312ce full CI 34080172455 succeeded.

Still unfinished: native concrete video-request assembly after an accepted frame,
live authorized provider generation, subsequent continuity frames, postproduction,
master QA and controlled release. No new full-SOP PASS or native QA claim.
