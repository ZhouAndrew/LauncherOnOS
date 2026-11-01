#!/usr/bin/env bash
# Linux Mint: new-system recovery backup with Borg 1.x deduplication.
# Back up user data, service data, OS/app settings and hardware/driver inventory.
# Does not format disks, prune archives, overwrite source data or modify drivers.
set -Eeuo pipefail
umask 077

TARGET='/media/andrew/HomeBackUp'
TARGET_UUID='6cb1c243-6bdb-4e82-9301-cf6231b87a66'
SYS_UUID='72922d41-9fcd-4685-babf-ab18dce04fa8'
REPO="$TARGET/Mint-Recovery-Borg"
DATA='/media/andrew/andrew'
DATA_UUID='4f011eda-d619-4d6a-875f-37a0d6fd1739'
MIN_FREE_GIB=20
MODE="${1:-backup}"

err() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }
capture() { local file="$1"; shift; ( "$@" > "$file" 2>&1 ) || printf 'NOTICE: 无法运行: %s\n' "$*" >> "$file"; }

[[ $(id -u) -eq 0 ]] || err '请使用 sudo bash 运行。'
for cmd in borg findmnt df blkid flock; do
  command -v "$cmd" >/dev/null 2>&1 || err "缺少 $cmd。请先运行 sudo apt install borgbackup util-linux"
done
[[ $(borg --version) =~ ^borg\ 1\. ]] || err '脚本使用 Borg 1.x 语法（Linux Mint 22 的 borgbackup 包提供 Borg 1.2）。'
[[ $(findmnt -n -o UUID -T /) == "$SYS_UUID" ]] || err '当前系统 UUID 与已确认设备不符，停止。'
[[ -d "$TARGET" ]] || err '找不到 HomeBackUp 挂载路径。'
[[ $(findmnt -n -o TARGET -T "$TARGET") == "$TARGET" ]] || err 'HomeBackUp 不是独立的已挂载分区。'
[[ $(findmnt -n -o UUID -T "$TARGET") == "$TARGET_UUID" ]] || err 'HomeBackUp UUID 不符，停止。'
[[ $(findmnt -n -o FSTYPE -T "$TARGET") == btrfs ]] || err 'HomeBackUp 不是 Btrfs。'
[[ $(findmnt -n -o OPTIONS -T "$TARGET") == *rw* ]] || err 'HomeBackUp 为只读挂载。'

mkdir -p "$TARGET"
exec 9>"$TARGET/.mint-recovery.lock"
flock -n 9 || err '已有另一项备份正在进行。'

if [[ "$MODE" == 'list' ]]; then
  [[ -d "$REPO" ]] || err '还没有备份仓库。'
  borg list "$REPO"
  exit 0
fi
if [[ "$MODE" == 'check' ]]; then
  [[ -d "$REPO" ]] || err '还没有备份仓库。'
  borg check --archives-only "$REPO"
  exit 0
fi
[[ "$MODE" == 'backup' || "$MODE" == '--with-data-disk' ]] || err '用法：sudo bash SCRIPT [backup|--with-data-disk|list|check]'

FREE=$(df -B1 --output=avail "$TARGET" | tail -1 | tr -d '[:space:]')
(( FREE >= MIN_FREE_GIB * 1024 * 1024 * 1024 )) || err "备份盘可用空间不足 ${MIN_FREE_GIB} GiB。"
printf '备份盘当前可用：%s GiB\n' "$(( FREE / 1024 / 1024 / 1024 ))"
log '正在准备恢复资料（包含驱动信息）'
STAGE=$(mktemp -d /var/tmp/mint-recovery-inventory.XXXXXXXX)
cleanup() { rm -rf -- "${STAGE:-/nonexistent}"; }
trap cleanup EXIT
mkdir -m 700 "$STAGE/driver-inventory" "$STAGE/system-inventory" "$STAGE/database-exports"

capture "$STAGE/system-inventory/lsblk.txt" lsblk -o NAME,TYPE,FSTYPE,UUID,LABEL,SIZE,MOUNTPOINTS
capture "$STAGE/system-inventory/blkid.txt" blkid
capture "$STAGE/system-inventory/mounts.txt" findmnt --real
capture "$STAGE/system-inventory/apt-manual.txt" apt-mark showmanual
capture "$STAGE/system-inventory/dpkg-installed.txt" dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n'
capture "$STAGE/system-inventory/os-release.txt" cat /etc/os-release
capture "$STAGE/system-inventory/kernels.txt" bash -c 'uname -a; dpkg-query -W "linux-image*" "linux-headers*" 2>/dev/null || true'
for disk in /dev/sda /dev/sdb /dev/sdc /dev/sdd; do
  [[ -b "$disk" ]] || continue
  capture "$STAGE/system-inventory/$(basename "$disk")-partitions.sfdisk" sfdisk --dump "$disk"
done
if command -v pvs >/dev/null; then capture "$STAGE/system-inventory/lvm-physical.txt" pvs -o +pv_uuid; fi
if command -v vgs >/dev/null; then capture "$STAGE/system-inventory/lvm-groups.txt" vgs; fi
if command -v lvs >/dev/null; then capture "$STAGE/system-inventory/lvm-volumes.txt" lvs -a -o +devices; fi
if command -v vgcfgbackup >/dev/null; then
  ( cd "$STAGE/system-inventory" && vgcfgbackup -f 'lvm-%s.conf' ) || log '注意：LVM 元数据导出失败。'
fi

capture "$STAGE/driver-inventory/kernel.txt" uname -a
if command -v lspci >/dev/null; then capture "$STAGE/driver-inventory/pci-drivers.txt" lspci -nnk; fi
if command -v lsusb >/dev/null; then capture "$STAGE/driver-inventory/usb-devices.txt" lsusb; fi
if command -v dkms >/dev/null; then capture "$STAGE/driver-inventory/dkms-status.txt" dkms status; fi
if command -v lsmod >/dev/null; then capture "$STAGE/driver-inventory/modules-loaded.txt" lsmod; fi
if command -v ubuntu-drivers >/dev/null; then capture "$STAGE/driver-inventory/ubuntu-drivers.txt" ubuntu-drivers devices; fi
if command -v nvidia-smi >/dev/null; then capture "$STAGE/driver-inventory/nvidia.txt" nvidia-smi; fi
if command -v lpstat >/dev/null; then capture "$STAGE/driver-inventory/printers.txt" lpstat -t; fi
if command -v flatpak >/dev/null; then capture "$STAGE/system-inventory/flatpak-system.txt" flatpak list --columns=application,branch,origin,installation; fi
if command -v snap >/dev/null; then capture "$STAGE/system-inventory/snap.txt" snap list; fi
grep -Ei '(nvidia|dkms|firmware|hplip|printer|realtek|rtl[0-9]|broadcom|virtualbox|linux-modules)' \
  "$STAGE/system-inventory/dpkg-installed.txt" \
  > "$STAGE/driver-inventory/driver-related-packages.txt" || true
if [[ -d /usr/src ]]; then
  capture "$STAGE/driver-inventory/usr-src-tree.txt" find /usr/src -mindepth 1 -maxdepth 3 -type f -name dkms.conf
fi

# Local service databases need a logical export. Avoid copying active database directories raw.
DB_EXCLUDES=()
if [[ -d /var/lib/mysql ]] && (pgrep -x mariadbd >/dev/null || pgrep -x mysqld >/dev/null); then
  DUMP=$(command -v mariadb-dump || command -v mysqldump || true)
  [[ -n "$DUMP" ]] || err 'MariaDB/MySQL 正在运行，却找不到数据库导出命令。'
  log '导出运行中的 MariaDB/MySQL 数据库（若失败则终止）'
  "$DUMP" --all-databases --single-transaction --quick --routines --events --triggers --hex-blob \
    > "$STAGE/database-exports/mysql-all-databases.sql" || err '数据库导出失败；不会宣称完整备份。'
  [[ -s "$STAGE/database-exports/mysql-all-databases.sql" ]] || err '数据库导出文件为空。'
  DB_EXCLUDES+=( --exclude '/var/lib/mysql' )
fi
if [[ -d /var/lib/postgresql ]] && (pgrep -x postgres >/dev/null); then
  command -v pg_dumpall >/dev/null || err 'PostgreSQL 正在运行，却找不到 pg_dumpall。'
  log '导出 PostgreSQL 数据库'
  if id postgres >/dev/null 2>&1; then
    runuser -u postgres -- pg_dumpall > "$STAGE/database-exports/postgresql-all.sql" || err 'PostgreSQL 导出失败。'
  else
    err '无法确定 PostgreSQL 导出账户。'
  fi
  DB_EXCLUDES+=( --exclude '/var/lib/postgresql' )
fi

cat > "$STAGE/RESTORE-FIRST.txt" <<'TXT'
Linux Mint 新系统融合恢复备份
================================
此备份以重新安装 Linux Mint 为前提，包含 /home、常用系统配置、应用与服务数据、
驱动/硬件清单、驱动 DKMS 源码以及运行中的 MariaDB/PostgreSQL 数据库逻辑导出。
不要把旧 /etc、/usr/src、/var/lib 或旧内核模块整体覆盖到新系统！

推荐恢复顺序：
1. 重装 Mint，联网并升级；安装 borgbackup；挂载 HomeBackUp。
2. 用 borg list REPO 查看备份；在隔离目录解包，先恢复个人文件。
3. 检查 system-inventory/apt-manual.txt 与 dpkg-installed.txt，选择重新安装应用。
4. 检查 driver-inventory/*.txt，重新安装新内核兼容的 NVIDIA/Realtek/HPLIP 等。
5. 对 DKMS 通过包管理器重新安装，必要时从 /usr/src 中复用源码并重新编译。
6. 逐项恢复 /etc 的服务配置，重新部署数据库并导入 database-exports/*.sql。
7. 验收 Anki、Thunderbird、WordPress、Radicale、系统启动和设备驱动。

注意：这是文件级备份，不是磁盘镜像；不能代替实际恢复演练。
驱动、网络密钥、数据库和 /home 中可能有私密信息，必须保护 Borg 密码。
如果 Borg 备份密码遗失，无法解密备份。不要只把密码存在备份盘上。
/home 下动态写入的数据（尤其运行中的浏览器、Anki、Thunderbird）建议退出后备份。
其他分区 /dev/sdc7 默认不包含；使用 --with-data-disk 可选择增加其文件内容。
TXT

SOURCES=( /home /etc /usr/local /usr/src /opt /srv /root /var/lib /var/www /var/spool /boot "$STAGE" )
# /lib/firmware may be a symlink on merged-/usr installations; resolve it.
if [[ -d /lib/firmware ]]; then SOURCES+=( "$(readlink -f /lib/firmware)" ); fi
INCLUDED=()
for p in "${SOURCES[@]}"; do [[ -e "$p" ]] && INCLUDED+=( "$p" ); done
if [[ "$MODE" == '--with-data-disk' ]]; then
  [[ $(findmnt -n -o TARGET -T "$DATA") == "$DATA" ]] || err '外部数据盘未单独挂载，停止。'
  [[ $(findmnt -n -o UUID -T "$DATA") == "$DATA_UUID" ]] || err '外部数据盘 UUID 与记录不一致，停止。'
  INCLUDED+=( "$DATA" )
  log '已加入 /media/andrew/andrew；将尝试备份其文件，但容量可能不足。'
else
  log '本次仅备份系统盘用户数据、设置和应用服务（不含 /dev/sdc7）。'
fi

if [[ ! -d "$REPO" ]]; then
  log '初始化加密 Borg 仓库；请设置并妥善保存备份密码'
  borg init --encryption=repokey-blake2 "$REPO" || err 'Borg 仓库初始化失败。'
fi

NAME="mint-$(date -u +%Y%m%dT%H%M%SZ)"
log "开始去重压缩备份：$NAME"
# Prevent accidentally archiving running databases or rebuildable caches.
# Do not prune old archives or remove old files on the backup disk.
borg create --stats --progress --one-file-system --compression zstd,5 --exclude-caches \
  --exclude '/home/*/.cache' \
  --exclude '/home/*/.local/share/Trash' \
  --exclude '/var/cache' \
  --exclude '/var/lib/snapd/snap' \
  "${DB_EXCLUDES[@]}" \
  --exclude '/var/lib/snapd/cache' \
  --exclude '/var/lib/apt/lists' \
  "$REPO::$NAME" "${INCLUDED[@]}" || err "备份中断或有未成功读取的文件；请先运行 list 和 check 确认状态。"

log '验证 Borg 仓库归档结构'
borg list "$REPO::$NAME" >/dev/null || err '归档列表读取失败。'
borg check --archives-only --last 1 "$REPO" || err '归档元数据验证失败。'
log '归档创建成功（未进行完整文件恢复演练）'
printf '仓库：%s\n归档：%s\n' "$REPO" "$NAME"
printf '目标磁盘剩余：%s GiB\n' "$(($(df -B1 --output=avail "$TARGET" | tail -1 | tr -d '[:space:]') / 1024 / 1024 / 1024))"
printf '\n重要：请将 Borg 解密密码保存在备份盘之外，并在新系统上演练恢复！\n'
