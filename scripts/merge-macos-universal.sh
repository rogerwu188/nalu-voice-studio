#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
arm_bundle="${1:-}"
intel_bundle="${2:-}"
output_bundle="${3:-$repo_root/dist/Nalu Voice Studio.app}"

for bundle in "$arm_bundle" "$intel_bundle"; do
  if [[ -z "$bundle" || ! -d "$bundle" ]]; then
    echo "用法：$0 <arm64.app> <x86_64.app> [output.app]" >&2
    exit 1
  fi
done
if [[ "$output_bundle" != *.app || "$output_bundle" == "/" ]]; then
  echo "universal 输出必须是明确的 .app 路径" >&2
  exit 1
fi

arm_main="$arm_bundle/Contents/MacOS/NaluVoiceStudio"
intel_main="$intel_bundle/Contents/MacOS/NaluVoiceStudio"
arm_runtime="$arm_bundle/Contents/Resources/runtime/nalu-runtime"
intel_runtime="$intel_bundle/Contents/Resources/runtime/nalu-runtime"
arm_analyzer="$arm_bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
intel_analyzer="$intel_bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
arm_update_helper="$arm_bundle/Contents/Resources/updater/nalu-update-helper"
intel_update_helper="$intel_bundle/Contents/Resources/updater/nalu-update-helper"

lipo "$arm_main" -verify_arch arm64
lipo "$arm_runtime" -verify_arch arm64
lipo "$intel_main" -verify_arch x86_64
lipo "$intel_runtime" -verify_arch x86_64
lipo "$arm_analyzer" -verify_arch arm64
lipo "$intel_analyzer" -verify_arch x86_64
lipo "$arm_update_helper" -verify_arch arm64
lipo "$intel_update_helper" -verify_arch x86_64
cmp "$arm_bundle/Contents/Info.plist" "$intel_bundle/Contents/Info.plist"
cmp "$arm_bundle/Contents/Resources/update-trust.json" \
  "$intel_bundle/Contents/Resources/update-trust.json"
cmp "$arm_bundle/Contents/Resources/update-discovery.json" \
  "$intel_bundle/Contents/Resources/update-discovery.json"
diff -qr \
  "$arm_bundle/Contents/Resources/runtime-resources" \
  "$intel_bundle/Contents/Resources/runtime-resources"

if [[ -e "$output_bundle" ]]; then
  rm -rf "$output_bundle"
fi
mkdir -p "$(dirname "$output_bundle")"
ditto "$arm_bundle" "$output_bundle"

lipo "$arm_main" "$intel_main" -create \
  -output "$output_bundle/Contents/MacOS/NaluVoiceStudio"
lipo "$arm_runtime" "$intel_runtime" -create \
  -output "$output_bundle/Contents/Resources/runtime/nalu-runtime"
lipo "$arm_analyzer" "$intel_analyzer" -create \
  -output "$output_bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
lipo "$arm_update_helper" "$intel_update_helper" -create \
  -output "$output_bundle/Contents/Resources/updater/nalu-update-helper"
chmod 755 \
  "$output_bundle/Contents/MacOS/NaluVoiceStudio" \
  "$output_bundle/Contents/Resources/runtime/nalu-runtime" \
  "$output_bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
chmod 755 "$output_bundle/Contents/Resources/updater/nalu-update-helper"

codesign --force --sign - "$output_bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
codesign --force --sign - "$output_bundle/Contents/Resources/updater/nalu-update-helper"
codesign --force --sign - "$output_bundle/Contents/Resources/runtime/nalu-runtime"
codesign --force --sign - "$output_bundle/Contents/MacOS/NaluVoiceStudio"
codesign --force --sign - "$output_bundle"
lipo "$output_bundle/Contents/MacOS/NaluVoiceStudio" -verify_arch arm64 x86_64
lipo "$output_bundle/Contents/Resources/runtime/nalu-runtime" \
  -verify_arch arm64 x86_64
lipo "$output_bundle/Contents/Resources/analyzers/nalu-visual-analyzer" \
  -verify_arch arm64 x86_64
lipo "$output_bundle/Contents/Resources/updater/nalu-update-helper" \
  -verify_arch arm64 x86_64
codesign --verify --deep --strict --verbose=2 "$output_bundle"

echo "$output_bundle"
