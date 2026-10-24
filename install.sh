#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
dest="${HOME}/.local/bin/launcheronos"
mkdir -p -- "${HOME}/.local/bin"
if [[ $# -gt 1 || ( $# -eq 1 && ${1:-} != '--upgrade' ) ]]; then
  echo "Usage: bash install.sh [--upgrade]" >&2
  exit 2
fi
if [[ -e "$dest" || -L "$dest" ]]; then
  if [[ ${1:-} != '--upgrade' ]]; then
    echo "Existing installation: $dest (use --upgrade to replace a verified LauncherOnOS executable)" >&2
    exit 1
  fi
  if [[ -L "$dest" || ! -f "$dest" ]] || ! head -n 3 -- "$dest" | grep -Fq '"""LauncherOnOS:'; then
    echo "Refusing to replace an unrecognized executable: $dest" >&2
    exit 1
  fi
  backup="$(mktemp "${dest}.backup.XXXXXXXX")"
  cp -p -- "$dest" "$backup"
  echo "Previous CLI saved: $backup"
fi
staged="$(mktemp "${dest}.install.XXXXXXXX")"
trap 'rm -f -- "$staged"' EXIT
install -m 0755 -- "$script_dir/launcheronos.py" "$staged"
mv -f -- "$staged" "$dest"
echo "Installed: $dest"
echo "Run: $dest menu"
