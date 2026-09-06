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
