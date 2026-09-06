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
