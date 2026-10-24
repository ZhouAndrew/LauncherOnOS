#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
dest="$HOME/.local/bin/launcheronos"
mkdir -p -- "$HOME/.local/bin"
if [[ -e "$dest" || -L "$dest" ]]; then
  echo "Refusing to overwrite existing $dest" >&2
  exit 1
fi
install -m 0755 -- "$script_dir/launcheronos.py" "$dest"
echo "Installed: $dest"
echo "Run: $dest menu"
