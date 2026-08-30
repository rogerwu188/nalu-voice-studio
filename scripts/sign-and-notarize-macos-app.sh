#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="${1:-$repo_root/dist/Nalu Voice Studio.app}"
signing_identity="${NALU_SIGNING_IDENTITY:-}"
notary_profile="${NALU_NOTARY_PROFILE:-}"
notary_keychain="${NALU_NOTARY_KEYCHAIN:-}"
entitlements="${NALU_ENTITLEMENTS_PATH:-$repo_root/apps/macos/NaluVoiceStudio.entitlements}"

if [[ ! -d "$bundle" ]]; then
  echo "找不到应用：$bundle" >&2
  exit 1
fi
if [[ -z "$signing_identity" ]]; then
  echo "缺少 NALU_SIGNING_IDENTITY；正式发行必须使用 Developer ID Application 证书。" >&2
  exit 1
fi
if [[ ! -f "$entitlements" ]]; then
  echo "找不到签名权限文件：$entitlements" >&2
  exit 1
fi

runtime="$bundle/Contents/Resources/runtime/nalu-runtime"
executable="$bundle/Contents/MacOS/NaluVoiceStudio"
for signed_path in "$runtime" "$executable"; do
  if [[ ! -f "$signed_path" ]]; then
    echo "发布包缺少必须签名的可执行文件：$signed_path" >&2
    exit 1
  fi
done

# Sign from the inside out. Avoid --deep for production signing because it can hide
# unsigned nested code and apply the wrong entitlements to helpers.
codesign --force --options runtime --timestamp --sign "$signing_identity" "$runtime"
codesign --force --options runtime --timestamp --sign "$signing_identity" "$executable"
codesign \
  --force \
  --options runtime \
  --timestamp \
  --entitlements "$entitlements" \
  --sign "$signing_identity" \
  "$bundle"
codesign --verify --deep --strict --verbose=2 "$bundle"

if [[ -z "$notary_profile" ]]; then
  echo "Developer ID 签名已完成；未设置 NALU_NOTARY_PROFILE，因此没有声称已经公证。"
  exit 0
fi

notary_zip="$(mktemp -d)/Nalu-Voice-Studio-notary.zip"
ditto -c -k --keepParent "$bundle" "$notary_zip"
notary_arguments=(--keychain-profile "$notary_profile")
if [[ -n "$notary_keychain" ]]; then
  notary_arguments+=(--keychain "$notary_keychain")
fi
xcrun notarytool submit "$notary_zip" "${notary_arguments[@]}" --wait
xcrun stapler staple "$bundle"
xcrun stapler validate "$bundle"
codesign --verify --deep --strict --verbose=2 "$bundle"
spctl --assess --type execute --verbose=2 "$bundle"
echo "Developer ID 签名、公证和票据装订已完成"
