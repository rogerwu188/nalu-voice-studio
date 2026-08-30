#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
packaging_venv="$repo_root/.build/packaging-venv"

"$repo_root/scripts/check-macos-build-environment.sh"
python_path="$("$repo_root/scripts/find-python.sh")"

"$python_path" -m venv "$packaging_venv"
"$packaging_venv/bin/python" -m pip install --upgrade pip
"$packaging_venv/bin/python" -m pip install -e "$repo_root[packaging]"
PATH="$packaging_venv/bin:$PATH" "$repo_root/scripts/build-macos-app.sh"
if [[ -n "${NALU_SIGNING_IDENTITY:-}" ]]; then
  "$repo_root/scripts/sign-and-notarize-macos-app.sh" \
    "$repo_root/dist/Nalu Voice Studio.app"
fi
"$repo_root/scripts/verify-macos-release.sh" \
  "$repo_root/dist/Nalu Voice Studio.app"
ditto -c -k --keepParent \
  "$repo_root/dist/Nalu Voice Studio.app" \
  "$repo_root/dist/Nalu-Voice-Studio-macOS.zip"

shasum -a 256 \
  "$repo_root/dist/Nalu-Voice-Studio-macOS.zip" \
  >"$repo_root/dist/Nalu-Voice-Studio-macOS.zip.sha256"

echo "$repo_root/dist/Nalu-Voice-Studio-macOS.zip"
