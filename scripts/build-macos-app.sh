#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
app_root="$repo_root/apps/macos"
output_root="$repo_root/dist"
bundle="$output_root/Nalu Voice Studio.app"
release_version="${NALU_RELEASE_VERSION:-0.1.0}"
build_number="${NALU_BUILD_NUMBER:-1}"

"$repo_root/scripts/check-macos-build-environment.sh"

build_root="$repo_root/.build/nalu-macos"
binary_path="$build_root/NaluVoiceStudio"
visual_analyzer_path="$build_root/NaluVisualAnalyzer"
mkdir -p "$build_root"

runtime_binary="${NALU_RUNTIME_BINARY:-}"
if [[ -z "$runtime_binary" ]]; then
  if ! python3 -c 'import PyInstaller' >/dev/null 2>&1; then
    echo "PyInstaller is required. Run: python3 -m pip install -e '.[packaging]'" >&2
    exit 1
  fi
  python3 -m PyInstaller \
    --clean \
    --noconfirm \
    --onefile \
    --name nalu-runtime \
    --hidden-import nalu_runtime.app \
    --collect-all av \
    --collect-submodules uvicorn \
    --distpath "$build_root/runtime-dist" \
    --workpath "$build_root/pyinstaller-work" \
    --specpath "$build_root" \
    "$repo_root/scripts/nalu_runtime_entry.py"
  runtime_binary="$build_root/runtime-dist/nalu-runtime"
fi

if [[ ! -x "$runtime_binary" ]]; then
  echo "Bundled Runtime is missing or not executable: $runtime_binary" >&2
  exit 1
fi

swiftc -parse-as-library \
  "$app_root"/Sources/NaluVoiceStudio/*.swift \
  -framework SwiftUI \
  -framework AppKit \
  -framework AVFoundation \
  -framework Speech \
  -framework WebKit \
  -o "$binary_path"

swiftc \
  "$app_root/Sources/NaluVisualAnalyzer/main.swift" \
  -framework Vision \
  -framework CoreImage \
  -framework ImageIO \
  -o "$visual_analyzer_path"

if [[ -d "$bundle" && "$bundle" == "$output_root/"* ]]; then
  rm -rf "$bundle"
fi
mkdir -p \
  "$bundle/Contents/MacOS" \
  "$bundle/Contents/Resources/analyzers" \
  "$bundle/Contents/Resources/runtime" \
  "$bundle/Contents/Resources/runtime-resources"
cp "$binary_path" "$bundle/Contents/MacOS/NaluVoiceStudio"
cp "$runtime_binary" "$bundle/Contents/Resources/runtime/nalu-runtime"
cp "$visual_analyzer_path" \
  "$bundle/Contents/Resources/analyzers/nalu-visual-analyzer"
cp -R "$repo_root/configs" "$bundle/Contents/Resources/runtime-resources/configs"
cp -R "$repo_root/vendor" "$bundle/Contents/Resources/runtime-resources/vendor"
cp "$app_root/Info.plist" "$bundle/Contents/Info.plist"
/usr/libexec/PlistBuddy \
  -c "Set :CFBundleShortVersionString $release_version" \
  "$bundle/Contents/Info.plist"
/usr/libexec/PlistBuddy \
  -c "Set :CFBundleVersion $build_number" \
  "$bundle/Contents/Info.plist"

codesign --force --deep --sign - "$bundle"
echo "$bundle"
