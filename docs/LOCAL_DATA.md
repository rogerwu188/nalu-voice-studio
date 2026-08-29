# Local data and privacy boundary

Nalu Voice Studio is local-first. The native macOS application uses one SQLite
database as its project system of record:

```text
~/Library/Application Support/Nalu Voice Studio/nalu.sqlite3
```

Generated packages and Runtime working files are stored beside it under:

```text
~/Library/Application Support/Nalu Voice Studio/data/
```

The bundled Runtime listens only on `127.0.0.1`. Nalu has no database sync,
telemetry upload or automatic cloud backup path. The SQLite file must never be
placed in the application bundle, source repository or a shared temporary
directory.

## What can leave the Mac

The database itself is never sent to Qingshan or a model provider. A future
non-dry-run production operation may send only the approved script and selected
assets represented in that run's immutable production package. Paid generation
and publishing remain separate, fail-closed authorization scopes. Secrets belong
in macOS Keychain, not SQLite, project exports or production packages.

## Portable project backup

Use Nalu's project export rather than copying a live SQLite file. An export is a
versioned JSON envelope with a SHA-256 digest and currently contains the project,
seasons, episodes, script revisions, approval records, asset registry and
continuity snapshots, including versioned season-plan approvals. Import verifies
the format version and digest, rejects unknown tables, columns and cross-project
references, and restores the project atomically into a clean local database.

Exported asset records currently preserve local file references; they do not
embed or copy the media. A portable media bundle and complete privacy export are
still tracked by SOP-05 and must not be represented as complete.

## Development overrides

Source builds default to `./data/nalu.sqlite3`. Tests and developers may override
the locations with `NALU_DATABASE_PATH` and `NALU_DATA_ROOT`. The packaged macOS
app sets both values to the Application Support paths above before it starts the
bundled Runtime.

Schema changes are numbered migrations. Startup reconciles an interrupted
migration that added a column before its migration record was committed, so a
partial upgrade does not permanently prevent the user's local Runtime from
launching.
