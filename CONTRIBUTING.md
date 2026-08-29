# Contributing to Nalu Voice Studio

Thank you for helping make storytelling accessible to more people.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
pytest -q
scripts/build-macos-app.sh
```

## Pull requests

1. Open or reference an issue for user-visible changes.
2. Keep product code outside `vendor/qingshan/`.
3. Add tests for lifecycle, consent, paid-call, or continuity changes.
4. Update OpenAPI-facing models without silently breaking v1 clients.
5. Never commit credentials, personal media, voice samples, receipts, or model output.
6. Confirm `pytest`, `ruff`, and the Swift build pass.

## Production safety

Changes that can trigger paid generation, publish media, clone a voice, or use a
child's biometric data require a maintainer review. Paid execution must remain
fail-closed when approval or transaction evidence is incomplete.

## Imported Qingshan source

The pinned upstream import is traceability material. General fixes belong in a
new adapter or shared core module. If an imported file must change, explain why
the change cannot live in the productization layer and retain provenance.

## Commit style

Use short imperative subjects such as `Add episode approval guard`. A pull
request may contain multiple commits; maintainers may squash on merge.
