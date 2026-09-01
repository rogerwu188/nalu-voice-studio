#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$repo_root/dist/Nalu Voice Studio.app"
runtime="$bundle/Contents/Resources/runtime/nalu-runtime"
runtime_resources="$bundle/Contents/Resources/runtime-resources"
visual_analyzer="$bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
update_helper="$bundle/Contents/Resources/updater/nalu-update-helper"
update_trust="$bundle/Contents/Resources/update-trust.json"
update_discovery="$bundle/Contents/Resources/update-discovery.json"
smoke_root="$(mktemp -d)"
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
test -x "$update_helper"
test -f "$update_trust"
test -f "$update_discovery"
test -f "$runtime_resources/configs/feedback-export.json"
test -f "$runtime_resources/configs/qingshan-upstream.json"
test -f "$runtime_resources/vendor/qingshan/LICENSE"
"$repo_root/scripts/verify-macos-release.sh" "$bundle"
if "$update_helper" >/dev/null 2>&1; then
  echo "Update helper must fail closed without an explicit command" >&2
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

NALU_DATA_ROOT="$smoke_root/data" \
NALU_DATABASE_PATH="$smoke_root/nalu.sqlite3" \
NALU_REPOSITORY_ROOT="$runtime_resources" \
NALU_VISUAL_ANALYZER_BINARY="$visual_analyzer" \
  "$runtime" >"$smoke_root/runtime.log" 2>&1 &
runtime_pid=$!

for _ in {1..100}; do
  if curl --fail --silent http://127.0.0.1:8765/health >/dev/null; then
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
