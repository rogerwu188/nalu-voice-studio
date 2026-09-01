#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="${1:-$repo_root/dist/Nalu Voice Studio.app}"
expected_version="${NALU_RELEASE_VERSION:-}"
expected_build="${NALU_BUILD_NUMBER:-}"
require_developer_id="${NALU_REQUIRE_DEVELOPER_ID:-false}"
require_notarization="${NALU_REQUIRE_NOTARIZATION:-false}"
require_universal="${NALU_REQUIRE_UNIVERSAL:-false}"

plist="$bundle/Contents/Info.plist"
runtime="$bundle/Contents/Resources/runtime/nalu-runtime"
executable="$bundle/Contents/MacOS/NaluVoiceStudio"
visual_analyzer="$bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
update_helper="$bundle/Contents/Resources/updater/nalu-update-helper"
update_trust="$bundle/Contents/Resources/update-trust.json"
update_discovery="$bundle/Contents/Resources/update-discovery.json"
feedback_export="$bundle/Contents/Resources/runtime-resources/configs/feedback-export.json"
development_handoff="$bundle/Contents/Resources/runtime-resources/configs/development-handoff.json"

test -d "$bundle"
test -f "$plist"
test -x "$runtime"
test -x "$executable"
test -x "$visual_analyzer"
test -x "$update_helper"
test -f "$update_trust"
test -f "$update_discovery"
test -f "$feedback_export"
test -f "$development_handoff"
test -f "$bundle/Contents/Resources/runtime-resources/configs/qingshan-upstream.json"
test -f "$bundle/Contents/Resources/runtime-resources/vendor/qingshan/LICENSE"

bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist")"
version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$plist")"
build="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$plist")"
[[ "$bundle_id" == "studio.nalu.voice" ]]
[[ -z "$expected_version" || "$version" == "$expected_version" ]]
[[ -z "$expected_build" || "$build" == "$expected_build" ]]

[[ "$(/usr/bin/plutil -extract enabled raw "$feedback_export")" == "false" ]]
[[ "$(/usr/bin/plutil -extract administrator_authorized raw "$feedback_export")" == "false" ]]
[[ -z "$(/usr/bin/plutil -extract endpoint raw "$feedback_export")" ]]
[[ -z "$(/usr/bin/plutil -extract repository raw "$feedback_export")" ]]
[[ "$(/usr/bin/plutil -extract enabled raw "$development_handoff")" == "false" ]]
[[ "$(/usr/bin/plutil -extract administrator_authorized raw "$development_handoff")" == "false" ]]
[[ -z "$(/usr/bin/plutil -extract endpoint raw "$development_handoff")" ]]

codesign --verify --deep --strict --verbose=2 "$bundle"
if [[ "$require_universal" == "true" ]]; then
  lipo "$executable" -verify_arch arm64 x86_64
  lipo "$runtime" -verify_arch arm64 x86_64
  lipo "$visual_analyzer" -verify_arch arm64 x86_64
  lipo "$update_helper" -verify_arch arm64 x86_64
fi
authority="$(codesign -dv --verbose=4 "$bundle" 2>&1 | sed -n 's/^Authority=//p' | head -1)"
if [[ "$require_developer_id" == "true" && "$authority" != Developer\ ID\ Application:* ]]; then
  echo "发布校验要求 Developer ID，但当前签名不是 Developer ID Application。" >&2
  exit 1
fi
if [[ "$require_notarization" == "true" ]]; then
  xcrun stapler validate "$bundle"
  spctl --assess --type execute --verbose=2 "$bundle"
fi

echo "Nalu macOS 发布包校验通过：版本 $version ($build)"
