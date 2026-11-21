#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
: "${sdk:?Set ANDROID_SDK_ROOT to your Android SDK directory}"
tools="${JOURNAL_BUILD_TOOLS:-$sdk/build-tools/35.0.0}"
platform="${JOURNAL_ANDROID_JAR:-$sdk/platforms/android-35/android.jar}"
output="${1:-Journal-Three-Android.apk}"
case "$output" in /*) ;; *) output="$PWD/$output";; esac
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/classes" "$work/dex" "$(dirname "$output")"
"$tools/aapt2" compile --dir res -o "$work/res.zip"
manifest=AndroidManifest.xml
if [[ "${JOURNAL_BUILD_PREVIEW:-0}" == 1 ]]; then
  sed 's/package="com.journalthree"/package="com.journalthree.preview"/;
       s/com.journalthree.capture"/com.journalthree.preview.capture"/;
       s/android:label="日志三号"/android:label="日志三号 预览"/' "$manifest" > "$work/AndroidManifest.xml"
  manifest="$work/AndroidManifest.xml"
fi
"$tools/aapt2" link -I "$platform" --manifest "$manifest" -o "$work/base.apk" "$work/res.zip"
javac --release 8 -encoding UTF-8 -cp "$platform" -d "$work/classes" src/com/journalthree/*.java
find "$work/classes" -name '*.class' -print0 | xargs -0 "$tools/d8" --min-api 26 --lib "$platform" --output "$work/dex"
(cd "$work/dex" && "$tools/aapt" add "$work/base.apk" classes.dex)
"$tools/zipalign" -p -f 4 "$work/base.apk" "$work/aligned.apk"
keystore="${JOURNAL_KEYSTORE:-${XDG_DATA_HOME:-$HOME/.local/share}/journal-three/debug.keystore}"
if [[ ! -f "$keystore" ]]; then
  mkdir -p "$(dirname "$keystore")"
  keytool -genkeypair -keystore "$keystore" -storepass android -keypass android \
    -alias androiddebugkey -dname "CN=Journal Three Debug" -keyalg RSA -keysize 2048 -validity 10000
fi
"$tools/apksigner" sign --v4-signing-enabled false --ks "$keystore" --ks-pass pass:android --key-pass pass:android \
  --ks-key-alias androiddebugkey --out "$output" "$work/aligned.apk"
"$tools/apksigner" verify --verbose "$output"
