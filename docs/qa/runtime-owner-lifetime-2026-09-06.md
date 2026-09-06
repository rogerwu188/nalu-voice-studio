# Runtime owner lifetime — implementation, not acceptance

During isolated native replacement, terminating app PID 87085 left its bundled
Runtime processes 87110/87112 listening on QA port 18769. The next app correctly
refused to use that unowned process. Normal AppKit termination cleanup exists,
but a terminated/crashed app cannot rely on its termination notification.

The supervisor now owns the writer of a private stdin pipe passed only to its
Runtime and explicitly enables `NALU_RUNTIME_OWNER_PIPE=1`. Runtime watches EOF
and requests graceful Uvicorn shutdown. It never discovers/signals arbitrary PIDs,
claims another process or kills a listener by port. Standalone command-line use
without the flag is unchanged. App stop also closes the writer before existing
termination handling.

Local test starts two real loopback Runtime subprocesses with separate temporary
databases and no inherited credentials. Closing one pipe yields exit code 0,
the other remains healthy, and SQLite integrity is `ok`; closing the second
also yields exit code 0. Non-EOF bytes do not request shutdown. The integration
test passes in 1.91 seconds; ten existing port tests pass, Ruff and Swift parsing
pass. Full CI, frozen/PyInstaller pipe inheritance, native app crash/restart and
production-job recovery on the packaged candidate remain unverified. SOP-08 and
SOP-11 are not complete.

Follow-up: the full local Runtime suite passes **313 tests** (53.77s, two
dependency deprecation warnings). A packaged rehearsal command now reuses the
same dual-instance scenario against the exact app Runtime, binds evidence to its
binary SHA-256, and runs in arm64, x86_64 and Universal CI. Packaged startup has a
120-second bound. It passes the app's bundled resource registry explicitly, as
the real supervisor does; an initial harness attempt without that registry
failed during boot and is not cancellation evidence. Actual new-package results
and native app crash testing remain open.

The corrected harness against old `deb9cc0` arm64 package (ZIP SHA-256
`0c71cbd76a667ba399937bdee99aad9e83ff2f0f42c8cb61396513a17ea2b6d4`)
successfully started both instances, then failed specifically at the first
`wait(timeout=12)` after closing its owner pipe. This is the expected negative
control: old packaged Runtime does not react to EOF. The harness finally cleaned
up only its owned subprocesses; it did not produce a PASS receipt. New packaged
Runtime must pass the identical scenario before this checkpoint can close.

## New arm64 package and native crash/restart

Candidate `f49006265cd9ddd1ae3e27752a9713547abc5dd1`, CI `34056611147`,
arm64 artifact `9996185852`: packaged owner lifetime step passed. Downloaded ZIP
SHA-256 `1a8c9a624203237d9e8696b7f859f6da5b525f65bccb430e03968d593cc4498e`;
the included owner-lifetime report binds Runtime SHA-256
`99d92f8501ba737f1634737e205f023fa574002258d2324ed0331110a8297efa`.

Launched via macOS `open -n` with explicit isolated support `tmp.gEDfvkaLEc`
and port 18769, app PID 93509 owned bootloader 93518 and server 93520. Once
health returned 200/schema 27, SIGKILL was sent **only to the app PID**.
Both Runtime PIDs disappeared and the port refused connections after 0.63s;
no separate Runtime termination was needed for this new candidate.

Relaunch through the same system launcher produced app PID 93638 and Runtime
93650/93652. Health again returned 200/schema 27, the native window exposed two
project rows, and read-only SQLite inspection returned `integrity_check=ok`.
Both project IDs/titles matched the pre-crash baseline:
`prj_57a28cc17a4843879add31a0f43b7029` (未命名故事) and
`prj_c23554a23adf4cdca88394196f7d3349` (Synthetic QA B — no assets).

No microphone, speech recognition, provider request or production job was started.
This is bounded native owner-death/restart evidence, not in-flight paid-job recovery,
real voice acceptance or signed-release acceptance. Full x86_64/Universal CI still
needs final verification.
