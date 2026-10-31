#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ${EUID} -eq 0 ]]; then
    echo 'Run Mint Toolbox as your regular desktop user, without sudo.' >&2
    exit 1
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo 'Missing desktop components. Run: sudo apt install python3-tk zenity pkexec' >&2
    exit 1
fi
bash install.sh
exec python3 "$HOME/.local/share/mint-toolbox/toolbox.py" --plugins
