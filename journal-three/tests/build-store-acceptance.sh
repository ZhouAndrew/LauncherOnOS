#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
: "${sdk:?Set ANDROID_SDK_ROOT to your Android SDK directory}"
tools="${JOURNAL_BUILD_TOOLS:-$sdk/build-tools/35.0.0}"
platform="${JOURNAL_ANDROID_JAR:-$sdk/platforms/android-35/android.jar}"
key="${JOURNAL_KEYSTORE:-${XDG_DATA_HOME:-$HOME/.local/share}/journal-three/debug.keystore}"
output="${1:-StoreAcceptance.apk}"
case "$output" in /*) ;; *) output="$PWD/$output";; esac
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/main" "$work/test" "$work/dex" "$work/assets" "$(dirname "$output")"
javac --release 8 -encoding UTF-8 -cp "$platform" -d "$work/main" src/com/journalthree/*.java
javac --release 8 -encoding UTF-8 -cp "$platform:$work/main" -d "$work/test" tests/src/com/journalthree/*.java
find "$work/test" -name '*.class' -print0 | xargs -0 "$tools/d8" --min-api 26 \
    --lib "$platform" --classpath "$work/main" --output "$work/dex"
manifest=tests/AndroidManifest.xml
if [[ "${JOURNAL_BUILD_PREVIEW:-0}" == 1 ]]; then
  sed 's/android:targetPackage="com.journalthree"/android:targetPackage="com.journalthree.preview"/'     "$manifest" > "$work/AndroidManifest.xml"
  manifest="$work/AndroidManifest.xml"
fi
ffmpeg -nostdin -loglevel error -f lavfi -i "testsrc2=size=144x96:rate=12" -t 7 \
    -c:v libx264 -pix_fmt yuv420p -threads 1 -movflags +faststart "$work/assets/playback.mp4"
"$tools/aapt2" link -I "$platform" --manifest "$manifest" -A "$work/assets" -o "$work/base.apk"
(cd "$work/dex" && "$tools/aapt" add "$work/base.apk" classes.dex)
"$tools/zipalign" -f 4 "$work/base.apk" "$work/aligned.apk"
"$tools/apksigner" sign --v4-signing-enabled false --ks "$key" --ks-pass pass:android \
    --key-pass pass:android --ks-key-alias androiddebugkey --out "$output" "$work/aligned.apk"
