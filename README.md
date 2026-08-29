# Nalu Voice Studio · Nalu 语音短剧工坊

> 前台是一位耐心的语音采访者，后台是一套专业的多集短剧制片厂。

Nalu Voice Studio is an open-source, voice-first macOS studio for ordinary
creators, older adults, and children. A user speaks naturally to create a
project, plan a season, approve episode scripts, provide authorized character
media, and send each approved episode through a professional production line.

This repository begins by productizing the Qingshan production line behind a
stable local Runtime API. The macOS client consumes that API instead of calling
history-specific scripts directly.

## Product hierarchy

```text
Project
  └── Season
        └── Episode plan
              └── Approved episode script
                    └── Episode production package
                          └── Qingshan production run
                                └── QA-approved episode master
```

Project-level character, scene, prop, voice, style, and continuity assets are
inherited by episodes through immutable production-package snapshots.

## Repository layout

```text
apps/macos/             Native SwiftUI voice-interviewer client
contracts/              Versioned JSON schemas and state-machine docs
services/runtime_api/   FastAPI + SQLite local runtime
vendor/qingshan/        Pinned upstream production-line source
docs/                   Architecture, safety and migration decisions
tests/                  Runtime contract tests
```

## Runtime quick start

```bash
# Python 3.11 or newer is required.
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
nalu-runtime
```

Open `http://127.0.0.1:8765/docs` for the local OpenAPI explorer.

Build the unsigned local macOS application bundle:

```bash
scripts/build-macos-release.sh
open "dist/Nalu Voice Studio.app"
```

The release script creates a self-contained app and zip. It bundles the Python
Runtime, pinned Qingshan resources and local supervisor; users do not manually
start a server after launching the app. Building requires macOS 14+, Xcode
Command Line Tools and Python 3.11+. Python is a build dependency, not an
end-user runtime dependency.

The default runtime is safe and local:

- The macOS app stores its only project database at
  `~/Library/Application Support/Nalu Voice Studio/nalu.sqlite3` and run
  packages in the adjacent `data/` directory.
- The source-development command stores data under `./data/` unless its local
  path is explicitly overridden.
- The server binds to `127.0.0.1`.
- Production starts in `dry_run` mode.
- Paid generation requires an explicit approval record and a configured
  Qingshan durable transaction submitter.

Nalu does not synchronize or upload the SQLite database. Only material selected
for an explicitly approved production run may leave the Mac through a configured
model provider. See [local data and privacy](docs/LOCAL_DATA.md) for paths,
backup boundaries and deletion behavior.

## Initial API surface

- `POST /v1/projects`
- `POST /v1/project-plans` (atomic Project → Season → Episode bootstrap)
- `PATCH /v1/projects/{project_id}`
- `POST /v1/projects/{project_id}/archive`
- `GET /v1/projects/{project_id}/export`
- `POST /v1/project-imports`
- `POST /v1/projects/{project_id}/seasons`
- `PATCH /v1/seasons/{season_id}`
- `GET /v1/seasons/{season_id}/plan-revisions`
- `POST /v1/seasons/{season_id}/plan-approvals`
- `POST /v1/seasons/{season_id}/episodes`
- `PATCH /v1/episodes/{episode_id}`
- `POST /v1/episodes/{episode_id}/scripts`
- `POST /v1/episodes/{episode_id}/scripts/{revision}/approve`
- `GET /v1/episodes/{episode_id}/script-approvals`
- `POST /v1/projects/{project_id}/assets`
- `POST /v1/episodes/{episode_id}/continuity-snapshots`
- `POST /v1/episodes/{episode_id}/production-runs`
- `GET /v1/production-runs/{run_id}`
- `GET /v1/production-runs/{run_id}/events`
- `POST /v1/production-runs/{run_id}/cancel`
- `POST /v1/production-runs/{run_id}/resume`

Retryable project-plan and production-run mutations accept `Idempotency-Key`.
Paid production requires that header, and a key is cryptographically bound to
its original request so it cannot be reused with changed model or budget data.

Project completion is governed by [the product SOP](docs/PRODUCT_SOP.md). A
module, milestone, or green CI run is not treated as completion of the product.
The committed [OpenAPI contract](docs/openapi.json) must be regenerated with
`scripts/export-openapi.py` whenever an endpoint or schema changes; CI rejects
an unreviewed stale contract.

## Upstream

The production-line import is pinned to Qingshan release `v2026.08.29.1`.
See [NOTICE.md](NOTICE.md) for provenance and [docs/architecture.md](docs/architecture.md)
for the productization boundary.

## License

MIT. Biometric media, model outputs, and third-party services remain subject to
their own permissions and terms.
