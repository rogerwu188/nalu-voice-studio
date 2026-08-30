#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
candidates=()
if [[ -n "${NALU_PYTHON:-}" ]]; then
  candidates+=("$NALU_PYTHON")
fi
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  candidates+=("$repo_root/.venv/bin/python")
fi
candidates+=(python3.14 python3.13 python3.12 python3.11 python3)

for candidate in "${candidates[@]}"; do
  if ! command -v "$candidate" >/dev/null 2>&1; then
    continue
  fi
  resolved="$(command -v "$candidate")"
  if "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    >/dev/null 2>&1; then
    echo "$resolved"
    exit 0
  fi
done

echo "找不到 Python 3.11 或更高版本。可安装新版 Python，或设置 NALU_PYTHON=/完整路径/python。" >&2
exit 1
