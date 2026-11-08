#!/usr/bin/env bash
# HomeBackUp: monthly Borg backup; retain latest from each of last 3 backup days.
# Does NOT run backups, delete archives or change disk partitions at install time.
set -Eeuo pipefail
umask 077

# Root lock files are acquired through safe_lock.py without link following.


SRC='/home/andrew/Desktop/homebackup-borg-recovery.sh'
BIN='/usr/local/libexec/homebackup-borg-recovery.sh'
RUN='/usr/local/sbin/homebackup-monthly'
REPO='/media/andrew/HomeBackUp/Mint-Recovery-Borg'
DEST='/media/andrew/HomeBackUp'
DEST_UUID='6cb1c243-6bdb-4e82-9301-cf6231b87a66'
SECRET_DIR='/var/backups/homebackup-scheduler'
SECRET="$SECRET_DIR/passphrase"
SERVICE='/etc/systemd/system/homebackup-monthly.service'
TIMER='/etc/systemd/system/homebackup-monthly.timer'

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $(id -u) == 0 ]] || fail '需要 root 权限：sudo bash homebackup-setup-latest3.sh'
for cmd in borg findmnt blkid systemctl mount python3 flock; do command -v "$cmd" >/dev/null 2>&1 || fail "未安装命令: $cmd"; done
[[ -r "$SRC" ]] || fail "找不到原备份脚本: $SRC（请确认它仍在桌面）。"
bash -n "$SRC" || fail '原备份脚本语法检查失败。'
[[ $(findmnt -n -o TARGET -T "$DEST" 2>/dev/null || :) == "$DEST" ]] || fail '请先在文件管理器挂载 HomeBackUp 再安装。'
[[ $(findmnt -n -o UUID -T "$DEST" 2>/dev/null || :) == "$DEST_UUID" ]] || fail 'HomeBackUp 分区 UUID 不符。'
[[ -d "$REPO" && -f "$REPO/config" ]] || fail '找不到已有 Borg 仓库，拒绝初始化或创建新的仓库。'
[[ $(borg --version) =~ ^borg\ 1\. ]] || fail '要求 Borg 1.x（Linux Mint 当前为 1.2.8）。'
if systemctl is-active --quiet homebackup-monthly.service 2>/dev/null; then
  fail '定时备份目前正在执行，禁止在运行期间更新脚本。'
fi

# Passphrase is required for unattended backups. Keep the secret OUT of paths
# included by the current backup script. /var/backups is not backed up by it.
install -d -m 700 -o root -g root "$SECRET_DIR"
tmp_secret=$(mktemp "$SECRET_DIR/.passphrase.XXXXXXXX")
trap 'rm -f -- "${tmp_secret:-}"' EXIT
chmod 600 "$tmp_secret"
if [[ -t 0 ]]; then
  printf '请输入当前 Borg 仓库密码（不回显，不会写入终端历史）：' >&2
  IFS= read -rs pass || fail '未读取密码。'
  printf '\n' >&2
  [[ -n "$pass" ]] || fail '密码不能为空。'
  printf '%s\n' "$pass" > "$tmp_secret"
  unset pass
else
  fail '请在交互式终端执行，以便安全输入 Borg 仓库密码。'
fi
# Validate before changing any systemd configuration; previous secret remains
# untouched on failure.
export BORG_PASSCOMMAND="/usr/bin/cat $tmp_secret"
if ! borg list --short "$REPO" >/dev/null 2>&1; then
  fail 'Borg 密码不正确，或者仓库读取失败；未修改定时任务。'
fi
unset BORG_PASSCOMMAND
mv -f -- "$tmp_secret" "$SECRET"
trap - EXIT
chmod 600 "$SECRET"

install -d -m 755 /usr/local/libexec
install -m 700 -o root -g root "$SRC" "$BIN"
install -m 700 -o root -g root "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/safe_lock.py" /usr/local/libexec/safe_lock.py

cat > "$RUN" <<'RUNNER'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

DEST='/media/andrew/HomeBackUp'
UUID='6cb1c243-6bdb-4e82-9301-cf6231b87a66'
REPO="$DEST/Mint-Recovery-Borg"
SECRET='/var/backups/homebackup-scheduler/passphrase'
SCRIPT='/usr/local/libexec/homebackup-borg-recovery.sh'
SELECTOR='/usr/local/libexec/homebackup-retention-select.py'
LOGPREFIX='[HomeBackUp]'

# Lock files are acquired safely by the verified no-follow launcher.


[[ $(id -u) == 0 ]] || { echo "$LOGPREFIX 必须以 root 运行" >&2; exit 1; }
[[ -r "$SECRET" ]] || { echo "$LOGPREFIX 无法读取 Borg 密码文件；停止。" >&2; exit 1; }
export BORG_PASSCOMMAND="/usr/bin/cat $SECRET"

# Avoid simultaneous scheduled runs, even before the backup disk is mounted.
SAFELOCK='/usr/local/libexec/safe_lock.py'
if [[ $(readlink /proc/self/fd/8 2>/dev/null || :) != /run/lock/homebackup-monthly.lock ]]; then
  exec /usr/bin/python3 -I "$SAFELOCK" 8 /run/lock/homebackup-monthly.lock /usr/bin/bash "$0" "$@"
fi
flock -n 8 || { echo "$LOGPREFIX 另一轮自动备份正在运行，取消本轮。" >&2; exit 1; }

# Attempt safe mount by an exact UUID. If absent/wrong, stop BEFORE writing.
if [[ $(findmnt -n -o TARGET -T "$DEST" 2>/dev/null || :) != "$DEST" ]]; then
  [[ -e "/dev/disk/by-uuid/$UUID" ]] || { echo "$LOGPREFIX 备份硬盘未连接；停止，不删除任何归档。" >&2; exit 1; }
  mkdir -p "$DEST"
  # Refuse to mask unrelated files on the underlying mountpoint.
  if [[ -n $(find "$DEST" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    echo "$LOGPREFIX 目标目录未挂载但非空；拒绝覆盖式挂载。" >&2; exit 1
  fi
  mount -t btrfs -o rw "UUID=$UUID" "$DEST" || { echo "$LOGPREFIX 无法挂载备份盘；停止。" >&2; exit 1; }
fi
[[ $(findmnt -n -o UUID -T "$DEST") == "$UUID" ]] || { echo "$LOGPREFIX 挂载 UUID 错误；停止。" >&2; exit 1; }
[[ $(findmnt -n -o FSTYPE -T "$DEST") == btrfs ]] || exit 1
[[ -d "$REPO" && -f "$REPO/config" ]] || { echo "$LOGPREFIX Borg 仓库不见了；拒绝初始化新仓库。" >&2; exit 1; }

# Only manage the 'mint-YYYYMMDDTHHMMSSZ' archives created by the recovery script.
# Selector examines Borg metadata, keeps newest archive per distinct local day,
# then keeps the three most recent days. Other archive families remain untouched.
plan() (
  path=$(mktemp /run/homebackup-selection.XXXXXXXX)
  trap 'rm -f -- "$path"' EXIT
  borg list --json "$REPO" > "$path"
  python3 "$SELECTOR" "$path"
)

if [[ ${1:-} == '--preview-prune' ]]; then
  echo "$LOGPREFIX 预览：每个备份日期保留最新一份，共最多 3 份；不执行删除。"
  plan
  exit 0
fi
if [[ ${1:-} == '--list' ]]; then
  borg list "$REPO"
  exit 0
fi
[[ $# == 0 ]] || { echo "用法: $0 [--preview-prune|--list]" >&2; exit 2; }

# Do not delete when backup fails, when Borg validation fails, or when the
# snapshot cannot be positively identified as newly created.
before=$(borg list --short --glob-archives 'mint-*' --sort-by timestamp "$REPO" | tail -n 1)
echo "$LOGPREFIX 备份开始，上一份最新归档：${before:-无}"
bash "$SCRIPT" backup
new=$(borg list --short --glob-archives 'mint-*' --sort-by timestamp "$REPO" | tail -n 1)
if [[ -z "$new" || "$new" == "$before" ]]; then
  echo "$LOGPREFIX 未确认新归档；本次绝不清理历史备份。" >&2
  exit 1
fi
[[ "$new" =~ ^mint-[0-9]{8}T[0-9]{6}Z$ ]] || { echo "$LOGPREFIX 新归档命名不符合保护范围，拒绝清理。" >&2; exit 1; }
borg info "$REPO::$new" >/dev/null
echo "$LOGPREFIX 正在校验新归档的文件数据；失败就不删除任何旧归档。"
borg check --archives-only --verify-data "$REPO::$new"

# Take one immutable plan based on metadata AFTER successful backup and check.
selection=$(mktemp /run/homebackup-selection.XXXXXXXX)
trap 'rm -f -- "${selection:-}" "${actions:-}"' EXIT
borg list --json "$REPO" > "$selection"
actions=$(mktemp /run/homebackup-actions.XXXXXXXX)
python3 "$SELECTOR" "$selection" > "$actions"
cat "$actions"
# Ensure the successfully verified new archive is on the KEEP list.
grep -Fxq "KEEP $new" "$actions" || { echo "$LOGPREFIX 最新归档未进入保留列表，拒绝删除。" >&2; exit 1; }

# Names were validated by selector (strict ASCII archive name) and are read
# without whitespace splitting; do not touch archives outside this family.
while IFS=' ' read -r op name; do
  [[ "$op" == DELETE ]] || continue
  [[ "$name" =~ ^mint-[0-9]{8}T[0-9]{6}Z$ ]] || exit 1
  echo "$LOGPREFIX 删除过期归档：$name"
  borg delete "$REPO::$name"
done < "$actions"
echo "$LOGPREFIX 清理无引用数据块..."
borg compact "$REPO"
echo "$LOGPREFIX 备份、校验、最多 3 份保留策略执行完成。"
df -h "$DEST"
RUNNER
chmod 700 "$RUN"
chown root:root "$RUN"

# Used for both preview and actual retention; fail closed on unknown metadata.
cat > /usr/local/libexec/homebackup-retention-select.py <<'PYSELECT'
#!/usr/bin/env python3
"""Select at most three latest daily mint-* Borg 1.x archives."""
import json
import re
import sys
from datetime import date

PATTERN = re.compile(r"mint-[0-9]{8}T[0-9]{6}Z\Z")


def select(data):
    entries = data.get("archives")
    if not isinstance(entries, list):
        raise ValueError("Borg JSON missing archives array")
    candidates = []
    for a in entries:
        name = a.get("name")
        if not isinstance(name, str):
            raise ValueError("Borg archive missing name")
        if not name.startswith("mint-"):
            continue
        if not PATTERN.fullmatch(name):
            raise ValueError("Unexpected mint-* archive name; refuse deletion: " + name)
        start = a.get("start")
        if not isinstance(start, str) or len(start) < 10:
            raise ValueError("Missing start time for " + name)
        # Borg 1.x uses local-time ISO timestamps in --json 'start'.
        day = date.fromisoformat(start[:10])
        candidates.append((name, day))
    if len({name for name, _ in candidates}) != len(candidates):
        raise ValueError("Duplicate archive name")
    # UTC YYYYMMDDTHHMMSSZ names sort chronologically, newest first.
    candidates.sort(reverse=True)
    selected_dates = set()
    keep = set()
    for name, day in candidates:
        if day not in selected_dates and len(selected_dates) < 3:
            selected_dates.add(day)
            keep.add(name)
    return [name for name, _ in candidates if name in keep], [name for name, _ in candidates if name not in keep]


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        keep, delete = select(json.load(f))
    for name in keep:
        print("KEEP " + name)
    for name in delete:
        print("DELETE " + name)
    print("保留 %d 份，计划删除 %d 份（仅 mint-* 归档）。" % (len(keep), len(delete)), file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print("保留策略解析失败，拒绝删除：" + str(exc), file=sys.stderr)
        sys.exit(1)
PYSELECT
chmod 700 /usr/local/libexec/homebackup-retention-select.py
chown root:root /usr/local/libexec/homebackup-retention-select.py

cat > "$SERVICE" <<'UNIT'
[Unit]
Description=HomeBackUp Borg monthly backup, max 3 daily archives
Documentation=https://borgbackup.readthedocs.io/en/1.2-maint/

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/homebackup-monthly
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
TimeoutStartSec=0
KillSignal=SIGINT
TimeoutStopSec=120
SendSIGKILL=no
UNIT

cat > "$TIMER" <<'UNIT'
[Unit]
Description=Monthly HomeBackUp recovery backup (3 retained)

[Timer]
OnCalendar=*-*-01 03:00:00
Persistent=true
RandomizedDelaySec=15min
AccuracySec=1min
Unit=homebackup-monthly.service

[Install]
WantedBy=timers.target
UNIT

chmod 644 "$SERVICE" "$TIMER"
systemctl daemon-reload
systemctl enable --now homebackup-monthly.timer
printf '\n已安装并启用每月备份；每月 1 日 03:00（系统本地时区）运行。\n'
printf '注意：由于 Persistent=true，如果已有日期被错过，首次启用时也可能立即补执行。\n'
printf '\n查看计划：sudo systemctl list-timers homebackup-monthly.timer\n'
printf '查看日志：sudo journalctl -u homebackup-monthly.service -n 100 --no-pager\n'
printf '预览删除：sudo /usr/local/sbin/homebackup-monthly --preview-prune\n'
printf '查看归档：sudo /usr/local/sbin/homebackup-monthly --list\n'
printf '暂停计划：sudo systemctl disable --now homebackup-monthly.timer\n'
printf '保留规则：最近 3 个有备份的日期，各保留当天最后一份；没有额外年度/月度保留。\n'
printf '\n重要：Borg 密码已存于 %s（仅 root 可读），必须另存离线恢复密码。\n' "$SECRET"
