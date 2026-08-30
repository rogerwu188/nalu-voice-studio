# Controlled release boundary

Nalu separates preparing a release from publishing it. A release package can be created
only after the production run is completed, the episode is `ready_to_publish`, the sealed
outputs still pass integrity checks, and the sealed MP4/caption structure report is bound
to the same output seal and has status `PASS`.

`POST /v1/production-runs/{run_id}/release-package` requires a title, description and
preparer identity. The seal must contain exactly one master video, captions file and
cover. The immutable package binds:

- production run, project and episode IDs;
- rendered-output seal SHA-256;
- media-structure QA report SHA-256;
- every sealed artifact path, kind, media type, size and SHA-256; and
- release title, description, preparer and timestamp.

The package always records `publishing_enabled: false` and an empty
`platform_approvals` list. Creating it never changes the episode to `published`, calls a
platform, uploads personal media or spends credits. Replaying the exact request returns
the same package; changed metadata, corrupted package state or changed sealed media fails
closed.

Future platform adapters must use a separate approval object for each destination. Child
projects require guardian approval at that later boundary. A platform response must bind
the approval, release-package digest, remote publication ID and reconciled state before
the episode can become `published`. None of those actions is implemented or implied by
the offline package.
