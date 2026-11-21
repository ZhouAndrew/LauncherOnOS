#!/usr/bin/env bash
set -euo pipefail

artifacts="${1:?Pass the directory containing both test APKs}"
adb install -r "$artifacts/Journal-Three-Preview.apk"
adb install -r "$artifacts/StoreAcceptance.apk"
adb shell wm dismiss-keyguard
timeout 180 adb shell am instrument -w com.journalthree.tests/com.journalthree.StoreAcceptance \
  | tee "$artifacts/android-acceptance.txt"
grep -q 'PASS: SQLite' "$artifacts/android-acceptance.txt"
grep -q 'PASS: continuous editor' "$artifacts/android-acceptance.txt"
grep -q 'PASS: tapped in-body' "$artifacts/android-acceptance.txt"
