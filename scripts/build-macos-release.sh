#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
packaging_venv="$repo_root/.build/packaging-venv"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The native macOS application must be built on macOS." >&2
  exit 1
fi
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Install Xcode Command Line Tools with: xcode-select --install" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required to assemble the self-contained Runtime." >&2
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "Python 3.11 or newer is required." >&2
  exit 1
}

python3 -m venv "$packaging_venv"
"$packaging_venv/bin/python" -m pip install --upgrade pip
"$packaging_venv/bin/python" -m pip install -e "$repo_root[packaging]"
PATH="$packaging_venv/bin:$PATH" "$repo_root/scripts/build-macos-app.sh"
ditto -c -k --keepParent \
  "$repo_root/dist/Nalu Voice Studio.app" \
  "$repo_root/dist/Nalu-Voice-Studio-macOS.zip"

echo "$repo_root/dist/Nalu-Voice-Studio-macOS.zip"
