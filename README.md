# Nalu Voice Studio · Nalu 语音短剧工坊

> 前台是一位耐心的语音创作采访者，后台是可更换的专业媒体生产线。

Nalu Voice Studio is an open-source, voice-first macOS studio for ordinary
creators, older adults, and children. A user speaks naturally to create a
project, choose short drama, documentary, animation, or commercial intent, approve scripts,
provide authorized media, and route each approved deliverable through a compatible
professional production line.

This repository begins by productizing the Qingshan production line behind a
stable local Runtime API. The macOS client consumes that API instead of calling
history-specific scripts directly.

The voice entrance, consent system, local project model, feedback loop, and pipeline
router are not coupled to Qingshan. Commercial projects currently fail closed at
production until an approved advertising adapter is installed. See
[creative pipeline routing](docs/CREATIVE_PIPELINE_ROUTING.md),
[Realtime voice architecture](docs/REALTIME_VOICE_ARCHITECTURE.md), and
[controlled product evolution](docs/CONTROLLED_EVOLUTION.md). Photos and scanned
handwriting become traceable, user-confirmed knowledge through the
[family memory library](docs/FAMILY_MEMORY_LIBRARY.md). Approved legacy scripts
use an evidence-bound, user-confirmed [continuity review](docs/CONTINUITY_REVIEW.md)
instead of asking the creator to complete a professional end-state form.
Completed renders are protected by a content-addressed
[output integrity seal](docs/RENDERED_OUTPUT_INTEGRITY.md) before release QA.

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

Build the local macOS application bundle:

```bash
scripts/build-macos-release.sh
open "dist/Nalu Voice Studio.app"
```

The release script creates a self-contained ad-hoc-signed app, zip and SHA-256 file. It bundles the Python
Runtime, pinned Qingshan resources and local supervisor; users do not manually
start a server after launching the app. Building requires macOS 14+, Xcode
and Python 3.11+. Python is a build dependency, not an
end-user runtime dependency.

Official distribution additionally requires Developer ID signing, hardened runtime and
Apple notarization. The fail-closed release workflow and credential setup are documented
in [the macOS release guide](docs/MACOS_RELEASE.md). A local build never claims to be an
official notarized release.

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
- `POST /v1/feedback` / `GET /v1/feedback`
- `POST /v1/feedback/{feedback_id}/review-bundle`
- `GET /v1/feedback/{feedback_id}/review-bundle`
- `POST /v1/feedback/{feedback_id}/triage`
- `GET /v1/feedback/{feedback_id}/triage`
- `POST /v1/feedback/{feedback_id}/external-export`
- `GET /v1/feedback/{feedback_id}/external-export`
- `POST /v1/feedback/{feedback_id}/external-export/reconciliation`
- `GET /v1/feedback/{feedback_id}/external-export/reconciliation`
- `POST /v1/feedback/{feedback_id}/development-work-order`
- `GET /v1/feedback/{feedback_id}/development-work-order`
- `POST /v1/feedback/{feedback_id}/development-handoff`
- `GET /v1/feedback/{feedback_id}/development-handoff`
- `POST /v1/feedback/{feedback_id}/development-handoff/reconciliation`
- `GET /v1/feedback/{feedback_id}/development-handoff/reconciliation`
- `POST /v1/feedback/{feedback_id}/development-result`
- `GET /v1/feedback/{feedback_id}/development-result`
- `POST /v1/feedback/{feedback_id}/release-linkage`
- `GET /v1/feedback/{feedback_id}/release-linkage`
- `POST /v1/projects/{project_id}/memory-cards`
- `PATCH /v1/memory-cards/{memory_id}`
- `POST /v1/memory-cards/{memory_id}/confirm`
- `POST /v1/project-plans` (atomic Project → Season → Episode bootstrap)
- `PATCH /v1/projects/{project_id}`
- `POST /v1/projects/{project_id}/archive`
- `GET /v1/projects/{project_id}/export`
- `GET /v1/projects/{project_id}/privacy-export`
- `GET /v1/projects/{project_id}/deletion-preview`
- `DELETE /v1/projects/{project_id}`
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
- `POST /v1/projects/{project_id}/asset-imports`
- `GET /v1/projects/{project_id}/assets`
- `GET /v1/assets/{asset_id}/consent-records`
- `POST /v1/assets/{asset_id}/consent-revocations`
- `GET /v1/assets/{asset_id}/dependencies`
- `DELETE /v1/assets/{asset_id}`
- `POST /v1/projects/{project_id}/library-entities`
- `GET /v1/projects/{project_id}/library-entities`
- `GET /v1/projects/{project_id}/library-entity-resolution`
- `GET /v1/library-entities/{entity_id}/revisions`
- `POST /v1/library-entities/{entity_id}/revisions`
- `POST /v1/library-entities/{entity_id}/confirmations`
- `POST /v1/episodes/{episode_id}/continuity-snapshots`
- `GET /v1/episodes/{episode_id}/continuity-snapshots`
- `GET /v1/episodes/{episode_id}/inherited-continuity`
- `POST /v1/episodes/{episode_id}/continuity-preflight`
- `POST /v1/episodes/{episode_id}/production-runs`
- `GET /v1/production-runs/{run_id}`
- `GET /v1/production-runs/{run_id}/events`
- `POST /v1/production-runs/{run_id}/cancel`
- `POST /v1/production-runs/{run_id}/resume`

Retryable project-plan and production-run mutations accept `Idempotency-Key`.
Paid production requires that header, and a key is cryptographically bound to
its original request so it cannot be reused with changed model or budget data.
When a dry-run caller omits the header, the Runtime assigns a stable internal
request identity so a restart recovers the exact run and package instead of
creating an orphan or duplicate.
Remote task persistence and restart semantics are documented in
[the durable recovery contract](docs/REMOTE_TASK_RECOVERY.md).
Failed release gates create persistent work according to
[the postproduction repair contract](docs/POSTPRODUCTION_REPAIR.md).
Preparing files never implies publication; see
[the controlled release boundary](docs/CONTROLLED_RELEASE.md).

Project completion is governed by [the product SOP](docs/PRODUCT_SOP.md). A
module, milestone, or green CI run is not treated as completion of the product.
The committed [OpenAPI contract](docs/openapi.json) must be regenerated with
`scripts/export-openapi.py` whenever an endpoint or schema changes; CI rejects
an unreviewed stale contract.

## Upstream

The production-line import is pinned to Qingshan release `v2026.08.29.1`.
See [NOTICE.md](NOTICE.md) for provenance and [docs/architecture.md](docs/architecture.md)
for the productization boundary. The provider-specific local contracts are documented in
[the Qingshan model compiler boundary](docs/QINGSHAN_MODEL_COMPILERS.md).

## License

MIT. Biometric media, model outputs, and third-party services remain subject to
their own permissions and terms.
