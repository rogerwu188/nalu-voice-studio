#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="${1:-$repo_root/dist/Nalu Voice Studio.app}"
signing_identity="${NALU_SIGNING_IDENTITY:-}"
notary_profile="${NALU_NOTARY_PROFILE:-}"
notary_keychain="${NALU_NOTARY_KEYCHAIN:-}"
entitlements="${NALU_ENTITLEMENTS_PATH:-$repo_root/apps/macos/NaluVoiceStudio.entitlements}"
update_public_key="${NALU_UPDATE_PUBLIC_KEY_BASE64:-}"
update_channel="${NALU_UPDATE_CHANNEL:-stable}"
update_origin="${NALU_UPDATE_ORIGIN:-}"

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
update_helper="$bundle/Contents/Resources/updater/nalu-update-helper"
update_trust="$bundle/Contents/Resources/update-trust.json"
update_discovery="$bundle/Contents/Resources/update-discovery.json"
visual_analyzer="$bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
semantic_recognizer="$bundle/Contents/Resources/recognizers/nalu-semantic-recognizer"
for signed_path in \
  "$runtime" "$executable" "$update_helper" "$visual_analyzer" "$semantic_recognizer"; do
  if [[ ! -f "$signed_path" ]]; then
    echo "发布包缺少必须签名的可执行文件：$signed_path" >&2
    exit 1
  fi
done
if [[ ! -f "$update_trust" ]]; then
  echo "发布包缺少更新信任配置：$update_trust" >&2
  exit 1
fi
if [[ ! -f "$update_discovery" ]]; then
  echo "发布包缺少更新发现配置：$update_discovery" >&2
  exit 1
fi
if [[ -z "$update_public_key" ]]; then
  echo "缺少 NALU_UPDATE_PUBLIC_KEY_BASE64；正式签名发行不能启用无可信公钥的更新。" >&2
  exit 1
fi
if [[ "$update_channel" != "stable" && "$update_channel" != "test" ]]; then
  echo "NALU_UPDATE_CHANNEL 必须是 stable 或 test。" >&2
  exit 1
fi
decoded_update_key="$(mktemp)"
trap 'rm -f "$decoded_update_key"' EXIT
if ! printf '%s' "$update_public_key" | /usr/bin/base64 -D >"$decoded_update_key" 2>/dev/null ||
   [[ "$(stat -f %z "$decoded_update_key")" != "32" ]]; then
  echo "NALU_UPDATE_PUBLIC_KEY_BASE64 必须是 32 字节 Ed25519 公钥。" >&2
  exit 1
fi
/usr/bin/plutil -replace enabled -bool YES "$update_trust"
/usr/bin/plutil -replace channel -string "$update_channel" "$update_trust"
/usr/bin/plutil -replace public_key_base64 -string "$update_public_key" "$update_trust"
/usr/bin/plutil -replace require_notarization -bool YES "$update_trust"
if [[ -n "$update_origin" ]]; then
  if [[ ! "$update_origin" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/([A-Za-z0-9._~-]+/)*$ ]]; then
    echo "NALU_UPDATE_ORIGIN 必须是无凭据、无查询或片段且以 / 结尾的 HTTPS 源。" >&2
    exit 1
  fi
  /usr/bin/plutil -replace enabled -bool YES "$update_discovery"
  /usr/bin/plutil -replace origin -string "$update_origin" "$update_discovery"
else
  /usr/bin/plutil -replace enabled -bool NO "$update_discovery"
  /usr/bin/plutil -replace origin -string "" "$update_discovery"
fi

# Sign from the inside out. Avoid --deep for production signing because it can hide
# unsigned nested code and apply the wrong entitlements to helpers.
codesign --force --options runtime --timestamp --sign "$signing_identity" "$runtime"
codesign --force --options runtime --timestamp --sign "$signing_identity" "$visual_analyzer"
codesign --force --options runtime --timestamp --sign "$signing_identity" "$semantic_recognizer"
codesign --force --options runtime --timestamp --sign "$signing_identity" "$update_helper"
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
