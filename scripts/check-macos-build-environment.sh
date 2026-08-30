#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Nalu 的原生 macOS 应用必须在 macOS 上构建。" >&2
  exit 1
fi

for command_name in swift swiftc codesign ditto; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少构建工具：$command_name" >&2
    exit 1
  fi
done

python_path="$("$repo_root/scripts/find-python.sh")"

if ! xcode-select -p >/dev/null 2>&1; then
  echo "没有可用的 Apple 开发工具。请安装 Xcode 后运行：sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
  exit 1
fi

# Merely finding swiftc is insufficient: a mismatched Command Line Tools install can
# compile ordinary Swift while failing to link PackageDescription. Exercise the exact
# package manifest used by Nalu so source builders get an actionable error before a
# lengthy PyInstaller build begins.
manifest_log="$(mktemp)"
if ! swift package --package-path "$repo_root/apps/macos" describe >"$manifest_log" 2>&1; then
  cat "$manifest_log" >&2
  rm -f "$manifest_log"
  echo >&2
  echo "Swift Package 工具链无法读取 Nalu。请安装完整 Xcode，接受许可，并选择正确的 Developer 目录：" >&2
  echo "  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
  echo "  sudo xcodebuild -license accept" >&2
  exit 1
fi
rm -f "$manifest_log"

echo "macOS 构建环境可用（Python：$python_path）"
