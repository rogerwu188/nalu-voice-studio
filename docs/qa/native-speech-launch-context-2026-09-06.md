# Native speech permission crash — open investigation

The isolated `deb9cc0` app PID 90994 exited with code 134. The macOS diagnostic
at 2026-09-06 13:00:25 local time identifies SIGABRT/TCC and says a speech
recognition usage description is absent. This is an actual failure, not PASS.

Contradictory evidence: direct `plutil` inspection of that exact app's
Contents/Info.plist shows nonempty `NSSpeechRecognitionUsageDescription` and
`NSMicrophoneUsageDescription`. The crash report identifies the Nalu bundle but
also names `codex` as parent and `ChatGPT` as responsible process. Thus blindly
adding the existing plist key is not a demonstrated fix. Direct executable launch
from the tool may affect privacy attribution; this is a hypothesis, not proven
root cause. The QA agent did not intentionally initiate recording in this run.

Following cleanup of only the two verified orphan QA Runtime PIDs 91006/91008,
the same app was launched through macOS `open -n` with explicit isolated QA
environment values. New app PID 93163 has parent PID 1; its own bundled Runtime
PIDs are 93210/93214. No permissions, microphone, provider request or secret read
was initiated during this relaunch. Successful Launch Services startup alone
does not prove the speech permission crash is fixed.

Next native voice QA must use Launch Services, observe consent and permission
behavior, and retain any new TCC evidence. Real speech/voice acceptance and SOP-02
remain IN_PROGRESS. Do not work around privacy protection or alter another app's
plist. The current owner-lifetime patch still needs new-package crash/restart QA.
