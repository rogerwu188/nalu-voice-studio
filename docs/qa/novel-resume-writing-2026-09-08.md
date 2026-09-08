# Novel resume preserves writing intent

The native resume branch previously reconstructed only an import command. This
lost an original combined import-and-write request after pausing or restarting.
It now reads persisted interactive turns and uses the latest web-source turn for
the exact imported URL to reconstruct the continuation. A project-switch guard
prevents applying an asynchronous lookup to a different project.

Added native tests cover same-source writing intent, repeated resume, missing
history, import-only history, and a different source. These tests await macOS CI;
local Swift compilation remains blocked by the documented SDK/toolchain mismatch.
`git diff --check` passes. No paid calls were made. Already-complete imports still
ask where to start writing rather than silently repeating a previous paid turn.
Installed pause/restart/resume-to-script QA remains required. No SOP is promoted.
