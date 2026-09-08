# Native repair reopening: not accepted

Artifact: CI 34279458243, commit 8c9e31810095e3cc53e95b2b142c9f797c8f6946,
arm64 ZIP SHA256 bc83bed47c1ba8cf8d7aaef5bed9a48c339c38047a8744ef86b954818e785fe2.
The arm64 job passed; whole CI was still running during this inspection.

Used the isolated support directory recorded in native-repair-fixture-2026-09-08.md,
port 18767. No installed app or user project was replaced. No provider call was made.

Native AX inspection showed the saved project at qa_review (60%). Opening
“本集怎么拍” and “把本集镜头剪在一起” did not restore saved editing state:
only the initial staging action appeared. Clicking “整理本集已采用的视频” returned
“暂时无法整理：请先确认每个镜头都已采用”. Repair confirmation was unreachable.

Code inspection confirms EpisodeEditingPanel does not automatically recover an
edit on reopening. EpisodeEditingModel.load first POSTs accepted-episode-inputs,
then reads the last edit. Thus access to existing downstream review/repair is
coupled to staging again. The precise reason staging failed in this synthetic
fixture is not yet established; this is not proof that all real projects fail.

Next: inspect the staging rejection and fixture validity, provide validated
read-only recovery of saved input/edit/picture state where appropriate, and repeat
native repair cancel/confirm/restart QA. Do not claim repair or any SOP complete.
The app was explicitly quit after this inspection.

Separate current source regression: novel import plus interactive story tests,
26 passed in 7.15 seconds. This does not validate actual model writing or video.
