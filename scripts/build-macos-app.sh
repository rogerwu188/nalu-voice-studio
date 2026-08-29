#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
app_root="$repo_root/apps/macos"
output_root="$repo_root/dist"
bundle="$output_root/Nalu Voice Studio.app"

build_root="$repo_root/.build/nalu-macos"
binary_path="$build_root/NaluVoiceStudio"
mkdir -p "$build_root"

swiftc -parse-as-library \
  "$app_root"/Sources/NaluVoiceStudio/*.swift \
  -framework SwiftUI \
  -framework AppKit \
  -framework AVFoundation \
  -framework Speech \
  -o "$binary_path"

mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp "$binary_path" "$bundle/Contents/MacOS/NaluVoiceStudio"
cp "$app_root/Info.plist" "$bundle/Contents/Info.plist"

codesign --force --deep --sign - "$bundle"
echo "$bundle"
