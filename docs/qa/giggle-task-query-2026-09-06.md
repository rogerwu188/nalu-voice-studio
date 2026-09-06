# Read-only Giggle task query

Status: IN_PROGRESS. No live query or paid generation executed.

Added the fixed GET `/api/v1/generation/task/query` transport following the
installed SD2 skill client. It receives a saved task identity and transient key,
disables redirects/proxy inheritance, bounds response size and sanitizes errors.
Pending, processing, completed, failed and error are distinct observations.
Unknown status, mismatched echoed task ID, duplicate JSON keys, missing completed
output or non-HTTPS/credential-bearing URLs are rejected. Returned URLs remain
untrusted download candidates; nothing is downloaded by this operation.

The observation always leaves billing_verified false. No failed response proves
zero charge and no completed URL is a verified master. It does not submit/retry
video requests. Eleven query tests and ten image-transport tests passed; Ruff
passed. Full regression launched separately and is not yet claimed passed.

Still required: project-scoped saved-binding endpoint, durable observation history,
native progress polling, bounded result retrieval, billing reconciliation, media
QA and complete user journey. CI 34064885482 for prior image transport candidate
5f2a1c8 was still running when observed.
