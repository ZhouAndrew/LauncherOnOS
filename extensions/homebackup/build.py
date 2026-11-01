from pathlib import Path
import re, shutil, os, subprocess
root=Path(__file__).resolve().parent / 'build-mint-homebackup-extension'
if root.exists(): shutil.rmtree(root)
base=root/'mint-homebackup-extension_0.1.2_all'
lib=base/'usr/lib/mint-homebackup-extension'
for sub in (lib,base/'usr/bin',base/'usr/share/applications',base/'etc/systemd/system',base/'DEBIAN'):
 sub.mkdir(parents=True,exist_ok=True)
(base/'DEBIAN').chmod(0o755)
source=(Path(__file__).resolve().parent / 'setup.sh').read_text()
backup=(Path(__file__).resolve().parent / 'backup.sh').read_text()
(lib/'backup.sh').write_text(backup)
(lib/'gui.py').write_text((Path(__file__).resolve().parent / 'gui.py').read_text())

# Reuse the field-tested source's 3-archive selector and runner, with new paths.
def heredoc(mark):
 match=re.search(r"cat > .*? <<'"+mark+r"'\n(.*?)\n"+mark+r"\n",source,re.S)
 assert match,mark
 return match.group(1)+'\n'
selector=heredoc('PYSELECT')
runner=heredoc('RUNNER')
runner=runner.replace('/usr/local/libexec/homebackup-borg-recovery.sh','/usr/lib/mint-homebackup-extension/backup.sh').replace('/usr/local/libexec/homebackup-retention-select.py','/usr/lib/mint-homebackup-extension/select.py')
(lib/'select.py').write_text(selector)
(lib/'run-backup').write_text(runner)
service='''[Unit]
Description=Mint HomeBackUp recovery backup (max 3 dates)
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/lib/mint-homebackup-extension/run-backup
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
TimeoutStartSec=0
'''
timer='''[Unit]
Description=Mint HomeBackUp monthly backup

[Timer]
OnCalendar=*-*-01 03:00:00
Persistent=true
RandomizedDelaySec=15min
AccuracySec=1min
Unit=mint-homebackup-extension.service

[Install]
WantedBy=timers.target
'''
(base/'etc/systemd/system/mint-homebackup-extension.service').write_text(service)
(base/'etc/systemd/system/mint-homebackup-extension.timer').write_text(timer)

admin='''#!/usr/bin/env bash
# Privileged entry point. No password is requested when installing the package.
set -Eeuo pipefail
umask 077
REPO='/media/andrew/HomeBackUp/Mint-Recovery-Borg'
DEST='/media/andrew/HomeBackUp'
UUID='6cb1c243-6bdb-4e82-9301-cf6231b87a66'
SECRETDIR='/var/backups/homebackup-scheduler'
SECRET="$SECRETDIR/passphrase"
RUN='/usr/lib/mint-homebackup-extension/run-backup'
OLD_TIMER='homebackup-monthly.timer'
NEW_TIMER='mint-homebackup-extension.timer'
fail(){ printf 'ERROR: %s\\n' "$*" >&2; exit 1; }
# Status is intentionally read-only and available to ordinary desktop users.
case ${1:-} in
  status)
    printf '每月定时器安装状态：'
    systemctl is-enabled "$NEW_TIMER" 2>/dev/null || printf '未找到\n'
    printf '每月定时器运行状态：'
    systemctl is-active "$NEW_TIMER" 2>/dev/null || printf '未运行\n'
    printf '旧定时器状态：'
    systemctl is-enabled "$OLD_TIMER" 2>/dev/null || printf '未找到\n'
    printf '备份磁盘挂载：'
    if [[ $(findmnt -n -o UUID -T "$DEST" 2>/dev/null || :) == "$UUID" ]]; then
      echo '已挂载正确磁盘'
    else
      echo '未挂载或 UUID 不符'
    fi
    systemctl list-timers "$NEW_TIMER" --all --no-pager 2>&1 || true
    exit 0;;
esac
[[ $(id -u) == 0 ]] || fail '该操作需要管理员授权。请从普通用户 GUI 通过授权对话框执行。'
[[ $(findmnt -n -o TARGET -T "$DEST" 2>/dev/null || :) == "$DEST" ]] || fail 'HomeBackUp 未挂载。'
[[ $(findmnt -n -o UUID -T "$DEST" 2>/dev/null || :) == "$UUID" ]] || fail '备份目标 UUID 不符。'
[[ $(findmnt -n -o FSTYPE -T "$DEST") == btrfs ]] || fail '目标不是 Btrfs。'
[[ -f "$REPO/config" ]] || fail '找不到原有 Borg 仓库；不会新建仓库。'
[[ $(borg --version) =~ ^borg\\ 1\\. ]] || fail '仅支持 Borg 1.x。'
case ${1:-} in
  enroll)
    # Reads exactly one Borg passphrase from stdin (not argv or env).
    install -d -m 700 -o root -g root "$SECRETDIR"
    tmp=$(mktemp "$SECRETDIR/.passphrase.XXXXXXXX")
    trap 'rm -f -- "$tmp"' EXIT
    chmod 600 "$tmp"
    IFS= read -r pass || fail '未收到 Borg 密码。'
    [[ -n "$pass" ]] || fail 'Borg 密码为空。'
    printf '%s\\n' "$pass" > "$tmp"
    unset pass
    export BORG_PASSCOMMAND="/usr/bin/cat $tmp"
    borg list --short "$REPO" >/dev/null || fail '解密验证失败，保持旧密码不变。'
    unset BORG_PASSCOMMAND
    mv -f "$tmp" "$SECRET"
    trap - EXIT
    chmod 600 "$SECRET"
    ;;
  use-existing)
    [[ -r "$SECRET" ]] || fail '尚未保存 Borg 密码；请先执行设置。'
    export BORG_PASSCOMMAND="/usr/bin/cat $SECRET"
    borg list --short "$REPO" >/dev/null || fail '已存 Borg 密码无效。'
    unset BORG_PASSCOMMAND
    ;;
  list|preview|check|verify-data|run|enable|disable)
    [[ -r "$SECRET" ]] || fail '请先设置 Borg 仓库密码。'
    export BORG_PASSCOMMAND="/usr/bin/cat $SECRET"
    ;;
  *) fail '用法: status|enroll|use-existing|list|preview|check|verify-data|run|enable|disable';;
esac
# Prevent duplicate monthly scheduled services; no automatic removal of older work.
case ${1:-} in
  enroll|use-existing|enable)
    if systemctl is-enabled --quiet "$OLD_TIMER" 2>/dev/null; then
      fail '检测到旧 homebackup-monthly.timer 已启用。请先人工停用旧定时器，防止重复备份。凭据已安全保存。'
    fi
    systemctl daemon-reload
    systemctl enable --now "$NEW_TIMER"
    echo '已启用新定时器；错过的月度任务可能立即补执行。';;
  list) "$RUN" --list;;
  preview) "$RUN" --preview-prune;;
  check)
    echo '开始检查 Borg 仓库归档结构；不会验证全部文件内容。'
    if borg check --archives-only "$REPO"; then
      echo '检查通过：归档结构正常。完整数据恢复尚未验证。'
    else
      code=$?
      echo "ERROR: 归档结构检查失败（退出码 $code）。" >&2
      exit "$code"
    fi;;
  verify-data)
    echo '开始执行 Borg 文件数据校验，可能需要很长时间。'
    if borg check --archives-only --verify-data "$REPO"; then
      echo '数据校验通过；尚未执行完整恢复演练。'
    else
      code=$?
      echo "ERROR: 深度数据校验失败（退出码 $code）。" >&2
      exit "$code"
    fi;;
  run) systemctl start mint-homebackup-extension.service;;
  disable) systemctl disable --now "$NEW_TIMER";;
esac
'''
(lib/'admin').write_text(admin)

client='''#!/usr/bin/env bash
# Graphical frontend by default; privileged operations use PolicyKit.
set -Eeuo pipefail
ADMIN='/usr/lib/mint-homebackup-extension/admin'
GUI='/usr/lib/mint-homebackup-extension/gui.py'
admin(){
  if [[ $(id -u) == 0 ]]; then "$ADMIN" "$@"; else /usr/bin/pkexec "$ADMIN" "$@"; fi
}
usage(){
 cat <<'HELP'
HomeBackUp Extension
  homebackup-ext               Open GTK 3 interface as normal user
  homebackup-ext gui           Same GUI
  homebackup-ext status        Read-only state; no sudo needed
  homebackup-ext setup         Save Borg password once and enable monthly timer
  homebackup-ext use-existing  Reuse existing verified password file
  homebackup-ext list          List Borg archives
  homebackup-ext preview       Preview retention only
  homebackup-ext backup        Trigger a backup
  homebackup-ext check         Validate archive structure
  homebackup-ext verify-data   Verify full archive data (slow)
  homebackup-ext enable        Enable monthly timer
  homebackup-ext disable       Disable monthly timer
Borg password and administrator authorization are different credentials.
HELP
}
setup(){
  if [[ -t 0 ]]; then
    printf '请输入 Borg 仓库解密密码（只输入一次，不会显示）：' >&2
    IFS= read -rs pass
    printf '\n' >&2
  else
    IFS= read -r pass || { echo '未收到密码。' >&2; exit 1; }
  fi
  [[ -n "${pass:-}" ]] || { echo '密码不能为空。' >&2; exit 1; }
  # Password passes through standard input only; not command args or environment.
  if [[ $(id -u) == 0 ]]; then
    printf '%s\n' "$pass" | "$ADMIN" enroll
  else
    printf '%s\n' "$pass" | /usr/bin/pkexec "$ADMIN" enroll
  fi
  unset pass
}
cmd=${1:-gui}
case "$cmd" in
  gui|menu) exec /usr/bin/python3 "$GUI";;
  status) "$ADMIN" status;;
  setup) setup;;
  use-existing) admin use-existing;;
  list) admin list;;
  preview) admin preview;;
  backup) admin run;;
  check) admin check;;
  verify-data) admin verify-data;;
  enable) admin enable;;
  disable) admin disable;;
  --help|-h|help) usage;;
  *) usage; exit 2;;
esac
'''
(base/'usr/bin/homebackup-ext').write_text(client)
(base/'usr/share/applications/mint-homebackup-extension.desktop').write_text('''[Desktop Entry]
Type=Application
Name=HomeBackUp Manager
Name[zh_CN]=HomeBackUp 备份管理器
Comment=Manage monthly Borg backups and recovery archives
Comment[zh_CN]=管理每月 Borg 备份与历史归档
Exec=homebackup-ext gui
Terminal=false
Icon=drive-harddisk
Categories=System;Utility;
Keywords=backup;borg;Mint;备份;恢复;
''')
control='''Package: mint-homebackup-extension
Version: 0.1.2
Section: admin
Priority: optional
Architecture: all
Maintainer: HomeBackUp project <noreply@example.invalid>
Depends: bash, borgbackup (>= 1.2), python3, python3-gi, gir1.2-gtk-3.0, util-linux, systemd, pkexec, coreutils
Description: Standalone Linux Mint HomeBackUp management extension
 Manage the existing encrypted Borg repository with a monthly systemd timer,
 safe retention of latest three backup days, and separate password enrollment.
 No MintBox dependency and no data change during package installation.
'''
(base/'DEBIAN/control').write_text(control)
postinst='''#!/bin/sh
set -e
case "$1" in
 configure)
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
  fi
  ;;
esac
exit 0
'''
(base/'DEBIAN/postinst').write_text(postinst)
prerm='''#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = deconfigure ]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now mint-homebackup-extension.timer 2>/dev/null || true
  fi
fi
exit 0
'''
(base/'DEBIAN/prerm').write_text(prerm)
# remove package files only on uninstall; root secret and Borg backup are never removed by package.
for f in [lib/'gui.py',lib/'backup.sh',lib/'select.py',lib/'run-backup',lib/'admin',base/'usr/bin/homebackup-ext',base/'DEBIAN/postinst',base/'DEBIAN/prerm']:
 f.chmod(0o755)
for f in [base/'etc/systemd/system/mint-homebackup-extension.service',base/'etc/systemd/system/mint-homebackup-extension.timer']:
 f.chmod(0o644)
readme='''# Mint HomeBackUp Extension 0.1.2

这是独立的 Linux Mint GTK 3 图形管理包，不依赖 MintBox。普通用户启动无需 sudo，查询定时器状态无需授权。安装不会初始化或修改已有 Borg 仓库，不主动删除任何归档，也不会自动开启定时备份。

**安装（一次系统管理员授权）：**

```bash
sudo apt install ./mint-homebackup-extension_0.1.2_all.deb
```

APT 可能因为 sudo 会话过期而要求管理员密码，但此安装包不会再次主动提示密码。它也不会在软件包安装环节要求 Borg 密码。

**一次性配置 Borg 仓库解锁**（这是独立于 Linux 管理员密码的第二种凭据）：

```bash
homebackup-ext setup
```

只输入一次 Borg 密码；通过 root 权限验证后写入仅 root 可读的 `/var/backups/homebackup-scheduler/passphrase`。使用 PolicyKit 执行授权操作，可能会另要求管理员授权。此密码必须在备份盘之外另行安全保存。如果此前运行过 `homebackup-setup-latest3.sh` 并留有有效的密码文件，可改用：

```bash
homebackup-ext use-existing
```

**图形管理：** 普通用户执行 `homebackup-ext` 或从 Mint 应用菜单运行 `HomeBackUp 备份管理器`。

系统定时器：每月 1 日 03:00，Persistent=true（错过日期后开机补执行），最多保留三个不同备份日期的最新归档；只有新备份完成并通过内容验证后才能清理。其他命名的 Borg 归档、Timeshift 快照和 HomeBackUp 盘内其他文件不受处理。若检测到旧 `homebackup-monthly.timer` 仍启用，新版会拒绝激活以防重复执行。

**兼容与局限：** 当前绑定用户已确认的 `HomeBackUp` UUID 和 Borg 仓库路径，沿用既有备份脚本，不含 `/dev/sdc7`；需要在真实 Linux Mint 22.2 上验证软件安装、权限提示、备份、恢复。首次备份成功不等于完整恢复验收。

**卸载：** `sudo apt remove mint-homebackup-extension`；不会删除 Borg 仓库和密码文件（保留恢复能力）。
'''
(Path(__file__).resolve().parent / 'BUILD-NOTES.md').write_text(readme)
print('generated',base)

# Manager source recipe: publish a deterministic Debian package to --output-dir.
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Build HomeBackUp Debian extension')
    parser.add_argument('--output-dir', type=Path, default=root.parent)
    args = parser.parse_args()
    dest = args.output_dir.expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    epoch = 1793404800
    for target in sorted(base.rglob('*'), reverse=True):
        os.utime(target, (epoch, epoch), follow_symlinks=False)
    os.utime(base, (epoch, epoch))
    subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group', '--build', str(base), str(dest / 'mint-homebackup-extension_0.1.2_all.deb')],
                   check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': str(epoch)})
