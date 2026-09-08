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

## Root cause and corrected fixture

The staging response was 409, `shot planning context is no longer current`:
the staging path requires preflight/waiting_for_approval, not qa_review.
The old fixture also ended with intentionally revoked recording/environment
consent. It must not be used as a valid-consent native happy-path fixture.
62851e2 preserves the fixture before those revocations (normal tests retain them).
New support: `/private/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-postproduction-qv1poe20`.

89cd1ec adds validated GET input-history recovery; 8a0da80 uses saved inputs
before staging. Swift tests were added, not yet accepted on the final artifact.

In the new fixture, the local picture-preview POST returned 200 / 9,491 bytes.
Receipt `evt_90f6418bd80948598be0553f427ae2f3` matched the existing approved edit
review; total picture-preview receipt count remained one. Preview SHA256 was
`a51d9b9bf2a78976959f85a6a58fc7adc932a986af6c1ea7678f057e389edb2c`.
This rerenders a local transient proxy, not a provider video or release master;
no read-only saved-file endpoint is claimed. Native reopening and repair remain
unaccepted until exercised on the updated application.

## Native f8fbfa7: recovery succeeds, player crashes

CI34281384986 arm64 artifact SHA256
`066018c1f837c0ec7a0bc01df840a928861ea3cfb649e77f5a9cbe9ccadd39bb`.
Isolated application at `/tmp/nalu-reopen-fixed-yaGYCv/extracted/Nalu Voice Studio.app`.
With the valid qv1poe20 fixture, opening editing and requesting saved inputs
restored both cuts (0.5–7.5 seconds and 0.5–6.5 seconds). Runtime logs showed
two GET events requests, no repeated accepted-input staging POST.

Clicking picture preview returned HTTP200 from the backend, then the native
process exited134: `failed to demangle superclass of VideoPlayerView from mangled
name 'So12AVPlayerViewC': unknown error`. Owned runtime shut down after the crash.
Crash report: `/Users/rogerwu/Library/Logs/DiagnosticReports/NaluVoiceStudio-2026-09-08-145547.ips`.
Repair confirmation was not reached. Next resolve native player loading and
repeat this exact journey; do not promote any SOP or claim full recovery PASS.

Candidate correction c1b3689 explicitly links AVKit in both the direct swiftc
release build and SwiftPM target. `otool -L` on the crashing binary showed
`_AVKit_SwiftUI` but no AVKit framework. The new per-architecture bundle check
rejects this old binary with `发布包缺少 AVKit 播放器框架链接：arm64`.
Both edited shell scripts pass `bash -n`; fixed binary playback remains unverified.

## Native 671d4c7 playback and repair submission

CI34283502068 arm64 ZIP SHA256
`d71b5c4d23f8e694b37eccdbe9658c47f399f350fbcac421693f9ee16cd5dae0`.
Application `/tmp/nalu-player-fixed-cScJ7d/extracted/Nalu Voice Studio.app`
explicitly links AVKit. On the same valid qv1poe20 fixture, saved cuts restored,
picture preview opened without the previous crash, and the play action was invoked.
The original edit approval and sound context restored. This is synthetic playback,
not semantic acceptance of a real episode.

Repair confirmation became reachable. Choosing cancel left SQLite with only
`run_frame_review|qa_review`. Reopening and confirming created
`run_ddfaf60101144e24bf5b2f90b3961549|preflight|dry_run=1` with no error; original
run remained qa_review. Parent-byte comparison and restart recovery are still next.
Sound selection displayed an unavailable message and repair instructions included
raw English: these remain unresolved. Full CI and final repaired master are not
accepted. No paid provider operation or release was performed by these actions.
