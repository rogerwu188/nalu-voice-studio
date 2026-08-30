# Rendered output integrity

Nalu keeps generated files outside SQLite but binds them to the local production
record with a content-addressed seal. This prevents a later character, scene,
prop, voice or style-library edit from silently rewriting the evidence for an
earlier render.

## Seal boundary

Only a production run in `qa_review` may create a seal. Candidate files must be
non-empty regular files under that run's managed
`qingshan-workspace/exports/` directory. Absolute paths, parent traversal,
symbolic links, duplicate paths and a set without exactly one master video fail
closed.

The immutable JSON seal binds:

- the production run, project and episode IDs;
- the canonical production-package hash;
- the confirmed project-library snapshot hash embedded in that package;
- the Qingshan workspace-manifest hash;
- each output's kind, path, MIME type, byte size and SHA-256 digest;
- the sealing actor and time; and
- a digest of the complete seal itself.

Creating the seal does not mark an episode publishable. Release-blocking
audiovisual QA must inspect the original-resolution master and then use this
integrity report as one input to the future completion transition.

## Verification and mutation behavior

`GET /v1/production-runs/{run_id}/rendered-output-integrity` recomputes the seal,
production package, library snapshot, workspace manifest and every artifact
digest. A modified or missing file produces `integrity_ok: false` and names the
failed path. An unreadable or structurally invalid seal fails closed.

A later confirmed project-library revision affects only future production
packages. It does not edit the sealed package or output bytes. The regression
fixture proves that the seal stays valid across such a library change and that
a subsequent output-byte mutation is detected.
