# Native accepted PCM audio transport — 2026-09-07

RuntimeClient now re-reads exact-take approval before requesting the accepted
audio export, preserving the caller's expected review ID. It downloads into a
temporary file, checks the bounded expected size before reading, removes the
temporary file on every completed path and returns typed bytes with take/review
identity, SHA-256 and sample count. No provider key or generation request is used.

The validator requires Runtime's canonical 44-byte PCM WAV header, 48 kHz stereo,
16-bit samples, exact data length, response SHA and exact take/review headers.
It rejects wrong HTTP status/MIME, cacheable results, malformed headers, mismatched
sample counts and invalid upper bounds before integer multiplication.

New native fixtures cover valid two-sample PCM, mismatched identity/hash/MIME/cache
headers, each structural WAV header field and zero/wrong/overflowing counts. The
existing client fixture verifies that historical acceptance causes only the
review GET and never requests audio bytes. These native tests await current CI.

Local backend actual-encode/export regression: 1 passed, 25 deselected, 21.28s.
Ruff/diff checks passed. CI 34102388611 for e68923c12fb5ab4a8debdc4da95938ab58a11617
had ARM and Runtime passing with Intel still running at the latest check.
Local native execution remains blocked by the recorded CommandLineTools errors.

This is a transport/validation integration point, not an installed playback or
alignment feature. Its downstream call site, speech alignment, subtitle review,
final mix/master/release and actual family QA remain required. No SOP is upgraded.
