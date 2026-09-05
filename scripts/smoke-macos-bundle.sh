#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$repo_root/dist/Nalu Voice Studio.app"
runtime="$bundle/Contents/Resources/runtime/nalu-runtime"
runtime_resources="$bundle/Contents/Resources/runtime-resources"
visual_analyzer="$bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
semantic_recognizer="$bundle/Contents/Resources/recognizers/nalu-semantic-recognizer"
update_helper="$bundle/Contents/Resources/updater/nalu-update-helper"
update_trust="$bundle/Contents/Resources/update-trust.json"
update_discovery="$bundle/Contents/Resources/update-discovery.json"
smoke_root="$(mktemp -d)"
fixture_root="$smoke_root/native-publication-fixture"
fixture_manifest="$smoke_root/native-publication-fixture.json"
publication_evidence="${NALU_PUBLICATION_FIXTURE_EVIDENCE:-$smoke_root/native-publication-fixture-qa.json}"
runtime_pid=""

cleanup() {
  if [[ -n "$runtime_pid" ]]; then
    kill "$runtime_pid" >/dev/null 2>&1 || true
    wait "$runtime_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

test -x "$runtime"
test -x "$visual_analyzer"
test -x "$semantic_recognizer"
test -x "$update_helper"
test -f "$update_trust"
test -f "$update_discovery"
test -f "$runtime_resources/configs/feedback-export.json"
test -f "$runtime_resources/configs/qingshan-upstream.json"
test -f "$runtime_resources/configs/production-adapters.json"
test -f "$runtime_resources/vendor/qingshan/LICENSE"
"$repo_root/scripts/verify-macos-release.sh" "$bundle"
if "$update_helper" >/dev/null 2>&1; then
  echo "Update helper must fail closed without an explicit command" >&2
  exit 1
fi
if "$semantic_recognizer" </dev/null >/dev/null 2>&1; then
  echo "Semantic recognizer must fail closed without a Runtime-issued request" >&2
  exit 1
fi
if "$update_helper" discover \
  --discovery-config "$update_discovery" \
  --trust-config "$update_trust" \
  --installed-build 1 \
  --state-root "$smoke_root/update-state" \
  --idempotency-key smoke-disabled-discovery-0001 >/dev/null 2>&1; then
  echo "Packaged update discovery must remain disabled without an authorized origin" >&2
  exit 1
fi

mkdir -p "$fixture_root"
python "$repo_root/scripts/create-native-publication-learning-fixture.py" \
  --root "$fixture_root" \
  --evidence "$fixture_manifest" >/dev/null

NALU_DATA_ROOT="$fixture_root/data" \
NALU_DATABASE_PATH="$fixture_root/nalu.sqlite3" \
NALU_REPOSITORY_ROOT="$runtime_resources" \
NALU_VISUAL_ANALYZER_BINARY="$visual_analyzer" \
NALU_SEMANTIC_RECOGNIZER_BINARY="$semantic_recognizer" \
  "$runtime" >"$smoke_root/runtime.log" 2>&1 &
runtime_pid=$!

for _ in {1..100}; do
  if curl --fail --silent http://127.0.0.1:8765/health >/dev/null; then
    project_id="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["project_id"])' "$fixture_manifest")"
    metrics_id="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["metrics_id"])' "$fixture_manifest")"
    curl --fail --silent "http://127.0.0.1:8765/v1/projects" >"$smoke_root/projects.json"
    curl --fail --silent \
      "http://127.0.0.1:8765/v1/projects/$project_id/director-strategies" \
      >"$smoke_root/strategies.json"
    curl --fail --silent \
      "http://127.0.0.1:8765/v1/publication-metrics/$metrics_id" \
      >"$smoke_root/metrics.json"
    python - \
      "$fixture_manifest" \
      "$smoke_root/projects.json" \
      "$smoke_root/strategies.json" \
      "$smoke_root/metrics.json" \
      "$publication_evidence" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path, projects_path, strategies_path, metrics_path, evidence_path = map(
    Path, sys.argv[1:]
)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
projects = json.loads(projects_path.read_text(encoding="utf-8"))
strategies = json.loads(strategies_path.read_text(encoding="utf-8"))
metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
assert [item["id"] for item in projects] == [manifest["project_id"]]
assert len(strategies) == 1
strategy = strategies[0]
assert strategy["source_metrics_id"] == manifest["metrics_id"]
assert strategy["requires_script_revision_and_approval"] is True
assert strategy["production_started"] is False
assert strategy["publication_performed"] is False
assert metrics["id"] == manifest["metrics_id"]
assert metrics["snapshot_sha256"] == strategy["source_metrics_sha256"]
assert metrics["read_only_sync_performed"] is True
assert metrics["production_performed"] is False
assert metrics["publication_performed"] is False
assert metrics["external_write_performed"] is False
report = {
    "schema_version": "nalu.packaged-publication-learning-qa/v1",
    "status": "PASS",
    "runtime_mode": "packaged",
    "project_id": manifest["project_id"],
    "metrics_id": manifest["metrics_id"],
    "strategy_id": manifest["strategy_id"],
    "checks": {
        "isolated_temporary_sqlite": True,
        "project_visible": True,
        "digest_link_valid": True,
        "script_reapproval_required": True,
        "read_only_flags_valid": True,
    },
    "network_scope": "loopback only; no provider, paid model, production or publication",
    "production_data_modified": False,
}
canonical = json.dumps(report, ensure_ascii=False, sort_keys=True)
report["report_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
evidence_path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
    echo "Bundled macOS Runtime smoke test passed"
    exit 0
  fi
  if ! kill -0 "$runtime_pid" >/dev/null 2>&1; then
    cat "$smoke_root/runtime.log" >&2
    exit 1
  fi
  sleep 0.1
done

cat "$smoke_root/runtime.log" >&2
echo "Bundled Runtime did not become healthy" >&2
exit 1
