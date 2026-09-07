# Native listening recovery and controls — 2026-09-07

RuntimeClient reads exact-take review recovery, validates current sound/edit/cue,
and separates historical review predecessors from effective current approval.
The observable model stages explicit decisions, preserves an uncertain POST,
reconciles matching saved results by GET and blocks new decisions after a failed
read. A prior take's accepted review cannot mark a replacement approved.

The existing recording panel now includes adopted/needs-adjustment controls,
readback confirmation and a saved-record recovery action. It uses incumbent
native large buttons, text wrapping, progress/disabled states and `.naluFont`.
Impeccable hardening guidance informed error/retry handling and preservation of
pending choices; no new professional form or voice-engine redesign was added.
Controls are hidden when the visible recording/offset differs from its saved
take and disabled during audition or parent attachment work.

Native fixture cases cover load-before-confirm, uncertain POST preservation,
matching GET reconciliation without a POST, old-take CAS predecessor retention,
and rejection of a falsely approved recovery response. Execution awaits native
CI; the backend encode/recording/recovery fixture passed (1 test, 25 deselected,
14.24s). Ruff/diff checks passed.

Local syntax verification could not run: `xcrun swiftc -frontend -parse` failed
on duplicate `SwiftBridging` declarations in CommandLineTools module maps,
before validating app code. The installed app is not updated and no screenshots,
keyboard/VoiceOver, actual listening or native end-to-end QA are claimed.
Do not treat the source wiring or synthetic backend result as a completed SOP.

CI 34100873064 for the two-source journey passed. CI 34101343116 had runtime and
ARM passing, Intel running at the latest check; newer commits require their own
native CI. Final alignment/mix/master/publication and real provider QA remain open.
