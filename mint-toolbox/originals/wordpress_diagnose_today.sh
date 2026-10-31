#!/usr/bin/env bash
# WordPress 故障只读排查脚本
# Version: 1.0.0

set -u
set -o pipefail

VERSION="1.0.0"
WP_PATH="/var/www/html/wordpress"
WEB_USER="www-data"
TODAY="$(date +%F)"
SINCE="${TODAY} 00:00:00"
UNTIL="${TODAY} 12:00:00"
REAL_USER="${SUDO_USER:-${USER:-$(id -un)}}"
REAL_HOME="$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6)"
REAL_HOME="${REAL_HOME:-$HOME}"
OUTPUT_DIR="${REAL_HOME}/Desktop"

usage() {
    cat <<'EOF'
用法：
  bash wordpress_diagnose_today.sh [选项]

选项：
  --wp-path PATH       WordPress 路径，默认 /var/www/html/wordpress
  --web-user USER      Web/PHP 运行用户，默认 www-data
  --since DATETIME     排查开始时间，默认今天 00:00:00
  --until DATETIME     排查结束时间，默认今天 12:00:00
  --output-dir DIR     报告保存目录，默认当前用户的 Desktop
  -h, --help           显示帮助

示例：
  bash wordpress_diagnose_today.sh
  bash wordpress_diagnose_today.sh \
    --since '2026-08-01 06:00:00' \
    --until '2026-08-01 10:30:00'
EOF
}

while (($#)); do
    case "$1" in
        --wp-path)
            WP_PATH="${2:?--wp-path 缺少参数}"
            shift 2
            ;;
        --web-user)
            WEB_USER="${2:?--web-user 缺少参数}"
            shift 2
            ;;
        --since)
            SINCE="${2:?--since 缺少参数}"
            shift 2
            ;;
        --until)
            UNTIL="${2:?--until 缺少参数}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:?--output-dir 缺少参数}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "错误：未知参数：$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if ! date -d "$SINCE" >/dev/null 2>&1; then
    echo "错误：无法识别开始时间：$SINCE" >&2
    exit 2
fi

if ! date -d "$UNTIL" >/dev/null 2>&1; then
    echo "错误：无法识别结束时间：$UNTIL" >&2
    exit 2
fi

if [[ "$(date -d "$UNTIL" +%s)" -le "$(date -d "$SINCE" +%s)" ]]; then
    echo "错误：结束时间必须晚于开始时间。" >&2
    exit 2
fi

if [[ ! -d "$WP_PATH" || ! -f "$WP_PATH/wp-config.php" ]]; then
    echo "错误：未找到有效 WordPress：$WP_PATH" >&2
    exit 2
fi

if ! command -v wp >/dev/null 2>&1; then
    echo "错误：未找到 WP-CLI（wp 命令）。" >&2
    exit 2
fi

if ! id "$WEB_USER" >/dev/null 2>&1; then
    echo "错误：系统中不存在用户：$WEB_USER" >&2
    exit 2
fi

mkdir -p "$OUTPUT_DIR" 2>/dev/null || true

if [[ ! -d "$OUTPUT_DIR" || ! -w "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="/tmp"
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="${OUTPUT_DIR}/wordpress_diagnose_${STAMP}.txt"

if command -v sudo >/dev/null 2>&1; then
    if ! sudo -v; then
        echo "错误：无法取得 sudo 权限。" >&2
        exit 1
    fi
else
    echo "错误：脚本需要 sudo。" >&2
    exit 1
fi

exec > >(tee "$REPORT") 2>&1

section() {
    printf '\n\n============================================================\n'
    printf '%s\n' "$1"
    printf '============================================================\n'
}

run() {
    printf '\n$'
    printf ' %q' "$@"
    printf '\n'

    "$@"
    local rc=$?

    if ((rc != 0)); then
        echo "[命令退出码：$rc]"
    fi

    return 0
}

wp_run() {
    sudo -u "$WEB_USER" -- wp --path="$WP_PATH" "$@"
}

service_log() {
    local service="$1"

    section "服务日志：$service（$SINCE 至 $UNTIL）"

    if systemctl list-unit-files --type=service 2>/dev/null |
        awk '{print $1}' |
        grep -qx "${service}.service"; then

        sudo journalctl \
            -u "$service" \
            --since "$SINCE" \
            --until "$UNTIL" \
            --no-pager
    else
        echo "未找到 ${service}.service，跳过。"
    fi
}

START_DATE="$(date -d "$SINCE" +%F)"
END_DATE="$(date -d "$UNTIL" +%F)"
APACHE_ACCESS_DATE="$(LC_ALL=C date -d "$SINCE" '+%d/%b/%Y')"
APACHE_ERROR_DAY="$(LC_ALL=C date -d "$SINCE" '+%b %d')"

section "报告信息"

echo "脚本版本：$VERSION"
echo "生成时间：$(date --iso-8601=seconds)"
echo "排查窗口：$SINCE  至  $UNTIL"
echo "WordPress：$WP_PATH"
echo "Web 用户：$WEB_USER"
echo "执行用户：$REAL_USER"
echo "报告文件：$REPORT"

section "系统概况"

run hostnamectl
run uname -a
run uptime
run free -h
run swapon --show
run df -hT "$WP_PATH" /tmp
run df -ih "$WP_PATH" /tmp
run systemctl --failed --no-pager

echo
echo "内存占用最高的进程："
ps aux --sort=-%mem | head -20

echo
echo "CPU 占用最高的进程："
ps aux --sort=-%cpu | head -20

section "今天的启动、关机与服务失败记录"

sudo last -x --time-format iso | head -40

section "内核异常：OOM、崩溃、磁盘与文件系统"

sudo journalctl \
    -k \
    --since "$SINCE" \
    --until "$UNTIL" \
    --no-pager |
grep -Ei \
    'out of memory|oom-kill|killed process|segfault|general protection|I/O error|buffer I/O|btrfs.*(error|corrupt)|ext4.*error|xfs.*error|nvme.*error|ata[0-9].*error|read-only file system' ||
echo "未发现匹配的内核严重异常。"

section "WordPress 基本状态"

run wp_run core version
run wp_run core verify-checksums
run wp_run core check-update
run wp_run option get home
run wp_run option get siteurl
run wp_run config get WP_CACHE
run wp_run config get WP_DEBUG
run wp_run config get WP_DEBUG_LOG

section "插件、主题和 Drop-in"

run wp_run plugin list \
    --fields=name,status,update,version,update_version \
    --format=table

run wp_run theme list \
    --fields=name,status,update,version,update_version \
    --format=table

run wp_run plugin verify-checksums --all

for file in \
    "$WP_PATH/wp-content/advanced-cache.php" \
    "$WP_PATH/wp-content/object-cache.php" \
    "$WP_PATH/wp-content/db.php" \
    "$WP_PATH/wp-content/sunrise.php"
do
    if [[ -e "$file" ]]; then
        echo
        sudo stat \
            -c '%A %U:%G %s bytes %y %n' \
            "$file"

        sudo head -n 25 "$file" 2>/dev/null || true
    fi
done

section "数据库检查"

run wp_run db check

section "Redis Object Cache"

run wp_run redis status

section "WP-Cron"

run wp_run cron event list \
    --fields=hook,next_run_gmt,next_run_relative,recurrence \
    --format=table

echo
echo "与备份、缓存、链接检查相关的 Cron："

wp_run cron event list \
    --fields=hook,next_run_gmt,next_run_relative,recurrence \
    --format=csv 2>/dev/null |
grep -Ei \
    'cache|redis|backup|updraft|wpvivid|blc|link|media|clean|delete' ||
true

section "排查时间窗口内修改的 WordPress 文件"

echo "核心文件："

sudo find \
    "$WP_PATH/wp-admin" \
    "$WP_PATH/wp-includes" \
    -type f \
    -newermt "$SINCE" \
    ! -newermt "$UNTIL" \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %u:%g %m %p\n' \
    2>/dev/null |
sort |
head -300

echo
echo "插件、MU 插件和主题："

sudo find \
    "$WP_PATH/wp-content/plugins" \
    "$WP_PATH/wp-content/mu-plugins" \
    "$WP_PATH/wp-content/themes" \
    -type f \
    -newermt "$SINCE" \
    ! -newermt "$UNTIL" \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %u:%g %m %p\n' \
    2>/dev/null |
sort -u |
head -500

echo
echo "wp-content 顶层 Drop-in："

sudo find \
    "$WP_PATH/wp-content" \
    -maxdepth 1 \
    -type f \
    -newermt "$SINCE" \
    ! -newermt "$UNTIL" \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %u:%g %m %p\n' \
    2>/dev/null |
sort -u

section "最近 14 天修改时间最晚的 WordPress 文件"

sudo find \
    "$WP_PATH/wp-admin" \
    "$WP_PATH/wp-includes" \
    "$WP_PATH/wp-content" \
    -type f \
    -mtime -14 \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %u:%g %m %p\n' \
    2>/dev/null |
sort -r |
head -300

section "上传、缓存和升级目录权限"

for dir in \
    "$WP_PATH/wp-content/uploads" \
    "$WP_PATH/wp-content/cache" \
    "$WP_PATH/wp-content/upgrade" \
    "$WP_PATH/wp-content/languages"
do
    if [[ -e "$dir" ]]; then
        echo
        sudo stat -c '%A %U:%G %n' "$dir"

        echo "其中 $WEB_USER 无法写入的目录（最多 100 条）："

        sudo -u "$WEB_USER" -- find \
            "$dir" \
            -type d \
            ! -writable \
            -printf '%U:%G %m %p\n' \
            2>/dev/null |
        head -100

        echo "其中 root 所有的文件或目录（最多 100 条）："

        sudo find \
            "$dir" \
            -user root \
            -printf '%u:%g %m %p\n' \
            2>/dev/null |
        head -100
    fi
done

section "WordPress Debug 日志"

DEBUG_LOG="$WP_PATH/wp-content/debug.log"

if [[ -f "$DEBUG_LOG" ]]; then
    sudo stat \
        -c '%A %U:%G %s bytes %y %n' \
        "$DEBUG_LOG"

    sudo tail -n 300 "$DEBUG_LOG"
else
    echo "未找到：$DEBUG_LOG"
fi

section "Apache 配置与 PHP"

run sudo apache2ctl configtest
run sudo apache2ctl -M
run php -v
run php --ini

echo
echo "关键 PHP 模块："

php -m |
grep -Ei \
    'curl|dom|exif|fileinfo|gd|intl|mbstring|mysqli|mysqlnd|opcache|redis|simplexml|xml|zip' ||
true

echo
echo "关键 PHP 配置："

php -i |
grep -Ei \
    '^(Loaded Configuration File|memory_limit|upload_max_filesize|post_max_size|max_execution_time|max_input_time|opcache.enable|opcache.memory_consumption|session.save_path)' ||
true

service_log apache2
service_log mysql
service_log redis-server
service_log caddy

section "Apache error.log：排查窗口内的错误"

if compgen -G '/var/log/apache2/error.log*' >/dev/null; then
    sudo zgrep \
        -hF "$APACHE_ERROR_DAY" \
        /var/log/apache2/error.log* \
        2>/dev/null |
    tail -1000

    echo
    echo "PHP/Apache 关键错误："

    sudo zgrep \
        -hEi \
        'PHP Fatal|PHP Parse|Uncaught|Allowed memory|Maximum execution|segmentation|segfault|permission denied|client intended to send too large body|AH[0-9]{5}|proxy:error|rewrite:error' \
        /var/log/apache2/error.log* \
        2>/dev/null |
    tail -1000
else
    echo "没有找到 /var/log/apache2/error.log*"
fi

section "Apache access.log：异常 HTTP 状态"

if compgen -G '/var/log/apache2/access.log*' >/dev/null; then
    sudo zcat \
        -f /var/log/apache2/access.log* \
        2>/dev/null |
    awk -v d="[$APACHE_ACCESS_DATE:" '
        index($4,d)==1 &&
        $9 ~ /^(400|401|403|404|408|409|413|429|500|501|502|503|504)$/ {
            print
        }
    ' |
    tail -1000

    echo
    echo "异常状态码计数："

    sudo zcat \
        -f /var/log/apache2/access.log* \
        2>/dev/null |
    awk -v d="[$APACHE_ACCESS_DATE:" '
        index($4,d)==1 &&
        $9 ~ /^(400|401|403|404|408|409|413|429|500|501|502|503|504)$/ {
            count[$9]++
        }
        END {
            for (s in count) {
                print s, count[s]
            }
        }
    ' |
    sort -n

    echo
    echo "5xx 请求最多的路径："

    sudo zcat \
        -f /var/log/apache2/access.log* \
        2>/dev/null |
    awk -v d="[$APACHE_ACCESS_DATE:" '
        index($4,d)==1 && $9 ~ /^5[0-9][0-9]$/ {
            count[$7]++
        }
        END {
            for (u in count) {
                print count[u], u
            }
        }
    ' |
    sort -nr |
    head -30
else
    echo "没有找到 /var/log/apache2/access.log*"
fi

section "系统软件包更新记录"

if compgen -G '/var/log/dpkg.log*' >/dev/null; then
    sudo zgrep \
        -hE "^(${START_DATE}|${END_DATE}) .* (install|upgrade|remove) " \
        /var/log/dpkg.log* \
        2>/dev/null |
    tail -500
fi

echo
echo "自动升级服务日志："

if systemctl list-unit-files --type=service 2>/dev/null |
    awk '{print $1}' |
    grep -qx 'unattended-upgrades.service'; then

    sudo journalctl \
        -u unattended-upgrades \
        --since "$SINCE" \
        --until "$UNTIL" \
        --no-pager
else
    echo "未找到 unattended-upgrades.service。"
fi

section "HTTP 实际访问测试"

HOME_URL="$(wp_run option get home 2>/dev/null || true)"
SITE_URL="$(wp_run option get siteurl 2>/dev/null || true)"

echo "home=$HOME_URL"
echo "siteurl=$SITE_URL"

if command -v curl >/dev/null 2>&1 && [[ -n "$HOME_URL" ]]; then
    echo

    curl \
        -k \
        -L \
        --max-time 30 \
        -o /dev/null \
        -sS \
        -w '正式网址：HTTP=%{http_code} DNS=%{time_namelookup}s connect=%{time_connect}s start=%{time_starttransfer}s total=%{time_total}s final=%{url_effective}\n' \
        "$HOME_URL" ||
    true

    echo

    curl \
        -k \
        -I \
        --max-time 30 \
        "$HOME_URL" \
        2>&1 |
    head -80
else
    echo "无法执行正式网址测试。"
fi

section "自动线索摘要"

OOM_COUNT="$(
    sudo journalctl \
        -k \
        --since "$SINCE" \
        --until "$UNTIL" \
        --no-pager \
        2>/dev/null |
    grep -Eic \
        'out of memory|oom-kill|killed process' ||
    true
)"

SEGFAULT_COUNT="$(
    sudo journalctl \
        -k \
        --since "$SINCE" \
        --until "$UNTIL" \
        --no-pager \
        2>/dev/null |
    grep -Eic \
        'segfault|general protection' ||
    true
)"

FAILED_COUNT="$(
    systemctl \
        --failed \
        --no-legend \
        2>/dev/null |
    grep -c . ||
    true
)"

CORE_CHANGED="$(
    sudo find \
        "$WP_PATH/wp-admin" \
        "$WP_PATH/wp-includes" \
        -type f \
        -newermt "$SINCE" \
        ! -newermt "$UNTIL" \
        2>/dev/null |
    wc -l
)"

CONTENT_CHANGED="$(
    sudo find \
        "$WP_PATH/wp-content/plugins" \
        "$WP_PATH/wp-content/mu-plugins" \
        "$WP_PATH/wp-content/themes" \
        -type f \
        -newermt "$SINCE" \
        ! -newermt "$UNTIL" \
        2>/dev/null |
    wc -l
)"

HTTP_5XX=0
HTTP_4XX=0

if compgen -G '/var/log/apache2/access.log*' >/dev/null; then
    HTTP_5XX="$(
        sudo zcat \
            -f /var/log/apache2/access.log* \
            2>/dev/null |
        awk -v d="[$APACHE_ACCESS_DATE:" '
            index($4,d)==1 && $9 ~ /^5[0-9][0-9]$/ {
                n++
            }
            END {
                print n+0
            }
        '
    )"

    HTTP_4XX="$(
        sudo zcat \
            -f /var/log/apache2/access.log* \
            2>/dev/null |
        awk -v d="[$APACHE_ACCESS_DATE:" '
            index($4,d)==1 && $9 ~ /^4[0-9][0-9]$/ {
                n++
            }
            END {
                print n+0
            }
        '
    )"
fi

printf 'OOM 相关记录：%s\n' "$OOM_COUNT"
printf '内核崩溃记录：%s\n' "$SEGFAULT_COUNT"
printf '当前 failed systemd units：%s\n' "$FAILED_COUNT"
printf '窗口内修改的核心文件：%s\n' "$CORE_CHANGED"
printf '窗口内修改的插件/MU/主题文件：%s\n' "$CONTENT_CHANGED"
printf '当天 Apache 4xx 数量：%s\n' "$HTTP_4XX"
printf '当天 Apache 5xx 数量：%s\n' "$HTTP_5XX"

echo

if (( OOM_COUNT > 0 )); then
    echo "[高优先级] 检测到 OOM/进程被杀记录，应优先检查内存和 swap。"
fi

if (( SEGFAULT_COUNT > 0 )); then
    echo "[高优先级] 检测到进程崩溃记录，应结合内核日志定位进程。"
fi

if (( HTTP_5XX > 0 )); then
    echo "[高优先级] Apache 访问日志中存在 5xx，请查看对应路径和 error.log。"
fi

if (( CORE_CHANGED > 0 )); then
    echo "[线索] 排查窗口内有核心文件变化，可能发生核心更新或覆盖。"
else
    echo "[排除项] 排查窗口内未发现核心文件变化。"
fi

if (( CONTENT_CHANGED > 0 )); then
    echo "[线索] 排查窗口内有插件、MU 插件或主题文件变化。"
else
    echo "[排除项] 排查窗口内未发现插件、MU 插件或主题文件变化。"
fi

if ((
    OOM_COUNT == 0 &&
    SEGFAULT_COUNT == 0 &&
    HTTP_5XX == 0 &&
    CORE_CHANGED == 0 &&
    CONTENT_CHANGED == 0
)); then
    echo "[提示] 未发现明显的更新、OOM、崩溃或 5xx；重点查看缓存、4xx、服务重启及特定请求。"
fi

section "完成"

echo "报告已保存：$REPORT"
echo "脚本没有修改 WordPress、数据库、缓存或服务配置。"

sudo chown \
    "$REAL_USER":"$(id -gn "$REAL_USER")" \
    "$REPORT" \
    2>/dev/null ||
true
