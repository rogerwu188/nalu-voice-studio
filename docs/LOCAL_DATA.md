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

Files selected in the native asset picker are copied into managed directories
under `data/assets/<project-id>/<asset-id>/`. Nalu validates the file name,
content type, size and resolved destination before recording it. The original
file may subsequently move without breaking the managed project copy.

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

The ordinary JSON project backup preserves asset records and managed local file
references, but intentionally does not embed media. Use the native **Privacy
Bundle** export when the subject needs a complete portable disclosure: its ZIP
contains the versioned project export, managed media and consent receipts, and
excludes SQLite files and secrets.

Face and voice imports require the subject name, an affirmative consent choice
and a written consent statement. Child projects additionally require guardian
approval. Revocation is retained as an audit receipt, marks the asset unusable,
and makes subsequent production fail closed. A production run stores an
immutable asset-dependency snapshot; Nalu refuses to delete any asset referenced
by such a snapshot.

Complete project deletion requires the user to type the exact project title. If
production snapshots exist, the request must also explicitly authorize deleting
them. Deletion stages project media and run directories, removes owned database
records transactionally, rolls files back if the transaction fails, and verifies
that the project, media and runs are absent before reporting success. The Runtime
contract and automated negative QA exist; a native deletion confirmation screen
is still tracked by SOP-05.

Provider API keys are stored as `WhenUnlockedThisDeviceOnly` items in the current
user's macOS Keychain. They are not read back into the settings interface and are
not passed to the Runtime at startup. The Runtime inherits only a small explicit
environment allowlist, so unrelated shell API keys and tokens cannot leak into
the bundled process. A future paid adapter must request its named key only after
the separate paid-action authorization gate.

Nalu creates the Application Support directory, SQLite database, managed media,
privacy exports and production packages with current-user-only POSIX modes
(`0700` directories and `0600` files). Cryptographic protection of these local
files relies on macOS volume encryption; enable FileVault for sensitive projects.
Nalu does not represent the files as application-layer encrypted when FileVault
is disabled. See [ADR 0003](adr/0003-local-secrets-and-at-rest-protection.md).

## Development overrides

Source builds default to `./data/nalu.sqlite3`. Tests and developers may override
the locations with `NALU_DATABASE_PATH` and `NALU_DATA_ROOT`. The packaged macOS
app sets both values to the Application Support paths above before it starts the
bundled Runtime.

Schema changes are numbered migrations. Startup reconciles an interrupted
migration that added a column before its migration record was committed, so a
partial upgrade does not permanently prevent the user's local Runtime from
launching.
