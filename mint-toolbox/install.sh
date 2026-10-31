#!/usr/bin/env bash
set -Eeuo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_dir="${HOME}/.local/share/mint-toolbox"
bin_dir="${HOME}/.local/bin"
desktop_dir="${HOME}/.local/share/applications"
mkdir -p -- "$bin_dir" "$desktop_dir" "$(dirname "$install_dir")"
if [[ "$source_dir" != "$install_dir" ]]; then
    stage="$(mktemp -d "${install_dir}.install.XXXXXXXX")"
    trap '[[ -n ${stage:-} && -d ${stage:-} ]] && rm -rf -- "$stage"' EXIT
    cp -a -- "$source_dir"/. "$stage"/
    if [[ -e "$install_dir" ]]; then
        backup="${install_dir}.backup.$(date +%Y%m%d-%H%M%S)"
        [[ ! -e "$backup" ]] || { echo "Backup already exists: $backup" >&2; exit 1; }
        mv -- "$install_dir" "$backup"
        echo "Previous installation backed up: $backup"
    fi
    mv -- "$stage" "$install_dir"
    stage=""
fi
chmod u+x -- "$install_dir/toolbox.py"
if [[ -e "$bin_dir/mint-toolbox" && ! -L "$bin_dir/mint-toolbox" ]]; then
    echo "Refusing to replace an unrelated executable: $bin_dir/mint-toolbox" >&2
    exit 1
fi
ln -sfn -- "$install_dir/toolbox.py" "$bin_dir/mint-toolbox"
cat > "$desktop_dir/mint-toolbox.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Mint Toolbox
Name[zh_CN]=Mint 实用工具集
Comment=Integrated personal utilities
Exec=$bin_dir/mint-toolbox --gui
Icon=applications-utilities
Terminal=false
Categories=Utility;
StartupNotify=true
EOF
chmod 644 "$desktop_dir/mint-toolbox.desktop"
echo "Installed Mint Toolbox in $install_dir"
echo "GUI: $bin_dir/mint-toolbox --gui"
echo "TUI: $bin_dir/mint-toolbox --tui"
echo "CLI: $bin_dir/mint-toolbox --list"
