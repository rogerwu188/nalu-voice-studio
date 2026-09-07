# Observed image result download and local storage

Status: IN_PROGRESS; backend and isolated/mock verification, not real production.

The image observation materialization endpoint accepts a saved observation ID and
result index, never an arbitrary download URL or destination path. It requires a
completed observation bound to an accepted image receipt and exact request hash.
The binding is checked again after download; archive or changed identity blocks
materialization. This does not authorize image generation or any paid retry.

The downloader reuses public-address validation and pins the validated IP while
retaining the original HTTPS hostname, certificate and SNI verification. Redirects
are limited and each destination is checked again. No provider credentials,
cookies or Authorization header are sent. Responses must be uncompressed PNG/JPEG,
at most 15 MB, and decode within 16 million pixels. Connection/read timeouts and
an elapsed-time budget limit network reads; system DNS resolution itself still
uses the OS resolver and is not a separately cancellable DNS worker.

Images are content-addressed under the run's `generated-images` directory, with
mode 0600, fsync and exclusive publication. Existing content is never overwritten.
Materialization events contain image hash/dimensions, observation/submission and
request bindings, filename and URL hash. They do not duplicate signed download
URLs. Identical requests after restart verify and reuse the existing local file;
missing or changed files require reconciliation rather than silent replacement.

Twelve targeted tests passed: credential-free pinned download, private redirect,
oversized declaration, HTML/invalid image, compressed response, completed download,
restart reuse, changed saved bytes, pending task, bad index, archive and failure.
Tests use synthetic provider receipts and an actual generated fixture PNG. No real
provider generation, downloaded customer image or fee is claimed.

Full local regression: 491 tests passed in 63.48 seconds. Ruff, exported OpenAPI
compatibility and SOP/progress structural audits passed. These checks do not
promote product SOP statuses or replace native/real-provider end-to-end QA.

Outstanding: native image preview/confirmation and production routing, visual
semantics/identity/frame acceptance, prior-final-frame continuity, full image cost
and upstream contracts, image-specific export/import recovery and real master/
release QA. A decoded/downloaded image remains explicitly unapproved visually.
