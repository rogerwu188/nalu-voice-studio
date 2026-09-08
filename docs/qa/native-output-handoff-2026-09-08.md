# Native output QA handoff — IN_PROGRESS

RuntimeClient.renderEpisodeMix now follows materialization with output sealing
of master, captions, postproduction manifest and shot manifest, then structural
and decoded-media QA. Reports must match run, seal and rendered master hashes
and report PASS. Failure throws to the existing recoverable exact-plan retry UI;
no final approval, speech QA, human acceptance or publication is performed.

Added deterministic seal-body and missing/unsafe-artifact native tests. Local
Swift toolchain remains incompatible; tests have not yet executed. Transport
failure/restart and actual encoded render-to-seal-to-QA fixture coverage remain
required. Existing renderer replay is idempotent, but full native recovery is
not yet accepted. No SOP promotion and no paid call.
