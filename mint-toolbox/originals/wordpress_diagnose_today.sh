#!/usr/bin/env bash
# WordPress read-only diagnostics
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
Usage:
  bash wordpress_diagnose_today.sh [options]

Options:
  --wp-path PATH       WordPress path; default: /var/www/html/wordpress
  --web-user USER      Web/PHP account; default: www-data
  --since DATETIME     Start time; default: today at 00:00:00
  --until DATETIME     End time; default: today at 12:00:00
  --output-dir DIR     Output directory; defaults to the current user's Desktop
  -h, --help           Show help

Examples:
  bash wordpress_diagnose_today.sh
  bash wordpress_diagnose_today.sh \
    --since '2026-08-01 06:00:00' \
    --until '2026-08-01 10:30:00'
EOF
}

while (($#)); do
    case "$1" in
        --wp-path)
            WP_PATH="${2:?--wp-path requires an argument}"
            shift 2
            ;;
        --web-user)
            WEB_USER="${2:?--web-user requires an argument}"
            shift 2
            ;;
        --since)
            SINCE="${2:?--since requires an argument}"
            shift 2
            ;;
        --until)
            UNTIL="${2:?--until requires an argument}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:?--output-dir requires an argument}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if ! date -d "$SINCE" >/dev/null 2>&1; then
    echo "Error: invalid start time: $SINCE" >&2
    exit 2
fi

if ! date -d "$UNTIL" >/dev/null 2>&1; then
    echo "Error: invalid end time: $UNTIL" >&2
    exit 2
fi

if [[ "$(date -d "$UNTIL" +%s)" -le "$(date -d "$SINCE" +%s)" ]]; then
    echo "Error: end time must be after start time." >&2
    exit 2
fi

if [[ ! -d "$WP_PATH" || ! -f "$WP_PATH/wp-config.php" ]]; then
    echo "Error: valid WordPress installation not found: $WP_PATH" >&2
    exit 2
fi

if ! command -v wp >/dev/null 2>&1; then
    echo "Error: WP-CLI (wp command) not found." >&2
    exit 2
fi

if ! id "$WEB_USER" >/dev/null 2>&1; then
    echo "Error: system account not found: $WEB_USER" >&2
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
        echo "Error: sudo authorization failed." >&2
        exit 1
    fi
else
    echo "Error: this script requires sudo." >&2
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
        echo "[Command exit code: $rc]"
    fi

    return 0
}

wp_run() {
    sudo -u "$WEB_USER" -- wp --path="$WP_PATH" "$@"
}

service_log() {
    local service="$1"

    section "Service log: $service($SINCE to $UNTIL)"

    if systemctl list-unit-files --type=service 2>/dev/null |
        awk '{print $1}' |
        grep -qx "${service}.service"; then

        sudo journalctl \
            -u "$service" \
            --since "$SINCE" \
            --until "$UNTIL" \
            --no-pager
    else
        echo "${service}.service not found; skipping."
    fi
}

START_DATE="$(date -d "$SINCE" +%F)"
END_DATE="$(date -d "$UNTIL" +%F)"
APACHE_ACCESS_DATE="$(LC_ALL=C date -d "$SINCE" '+%d/%b/%Y')"
APACHE_ERROR_DAY="$(LC_ALL=C date -d "$SINCE" '+%b %d')"

section "Report details"

echo "Script version: $VERSION"
echo "Generated at: $(date --iso-8601=seconds)"
echo "Diagnostic time window: $SINCE  to  $UNTIL"
echo "WordPress：$WP_PATH"
echo "Web account: $WEB_USER"
echo "Executing account: $REAL_USER"
echo "Report file: $REPORT"

section "System overview"

run hostnamectl
run uname -a
run uptime
run free -h
run swapon --show
run df -hT "$WP_PATH" /tmp
run df -ih "$WP_PATH" /tmp
run systemctl --failed --no-pager

echo
echo "Processes using the most memory:"
ps aux --sort=-%mem | head -20

echo
echo "Processes using the most CPU:"
ps aux --sort=-%cpu | head -20

section "Today's startup, shutdown, and service failures"

sudo last -x --time-format iso | head -40

section "Kernel issues: OOM, crashes, disks, and filesystems"

sudo journalctl \
    -k \
    --since "$SINCE" \
    --until "$UNTIL" \
    --no-pager |
grep -Ei \
    'out of memory|oom-kill|killed process|segfault|general protection|I/O error|buffer I/O|btrfs.*(error|corrupt)|ext4.*error|xfs.*error|nvme.*error|ata[0-9].*error|read-only file system' ||
echo "No matching critical kernel issues were found."

section "WordPress status"

run wp_run core version
run wp_run core verify-checksums
run wp_run core check-update
run wp_run option get home
run wp_run option get siteurl
run wp_run config get WP_CACHE
run wp_run config get WP_DEBUG
run wp_run config get WP_DEBUG_LOG

section "Plugins, themes, and drop-ins"

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

section "Database checks"

run wp_run db check

section "Redis Object Cache"

run wp_run redis status

section "WP-Cron"

run wp_run cron event list \
    --fields=hook,next_run_gmt,next_run_relative,recurrence \
    --format=table

echo
echo "Cron entries related to backup, cache, and link checking:"

wp_run cron event list \
    --fields=hook,next_run_gmt,next_run_relative,recurrence \
    --format=csv 2>/dev/null |
grep -Ei \
    'cache|redis|backup|updraft|wpvivid|blc|link|media|clean|delete' ||
true

section "WordPress files changed within the diagnostic window"

echo "Core files:"

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
echo "Plugins, MU plugins, and themes:"

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
echo "Top-level wp-content drop-ins:"

sudo find \
    "$WP_PATH/wp-content" \
    -maxdepth 1 \
    -type f \
    -newermt "$SINCE" \
    ! -newermt "$UNTIL" \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %u:%g %m %p\n' \
    2>/dev/null |
sort -u

section "Most recently modified WordPress files within 14 days"

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

section "Upload, cache, and upgrade directory permissions"

for dir in \
    "$WP_PATH/wp-content/uploads" \
    "$WP_PATH/wp-content/cache" \
    "$WP_PATH/wp-content/upgrade" \
    "$WP_PATH/wp-content/languages"
do
    if [[ -e "$dir" ]]; then
        echo
        sudo stat -c '%A %U:%G %n' "$dir"

        echo "Directories not writable by $WEB_USER (up to 100):"

        sudo -u "$WEB_USER" -- find \
            "$dir" \
            -type d \
            ! -writable \
            -printf '%U:%G %m %p\n' \
            2>/dev/null |
        head -100

        echo "Root-owned files or directories (up to 100):"

        sudo find \
            "$dir" \
            -user root \
            -printf '%u:%g %m %p\n' \
            2>/dev/null |
        head -100
    fi
done

section "WordPress debug log"

DEBUG_LOG="$WP_PATH/wp-content/debug.log"

if [[ -f "$DEBUG_LOG" ]]; then
    sudo stat \
        -c '%A %U:%G %s bytes %y %n' \
        "$DEBUG_LOG"

    sudo tail -n 300 "$DEBUG_LOG"
else
    echo "Not found: $DEBUG_LOG"
fi

section "Apache configuration and PHP"

run sudo apache2ctl configtest
run sudo apache2ctl -M
run php -v
run php --ini

echo
echo "Key PHP modules:"

php -m |
grep -Ei \
    'curl|dom|exif|fileinfo|gd|intl|mbstring|mysqli|mysqlnd|opcache|redis|simplexml|xml|zip' ||
true

echo
echo "Key PHP configuration:"

php -i |
grep -Ei \
    '^(Loaded Configuration File|memory_limit|upload_max_filesize|post_max_size|max_execution_time|max_input_time|opcache.enable|opcache.memory_consumption|session.save_path)' ||
true

service_log apache2
service_log mysql
service_log redis-server
service_log caddy

section "Apache error.log: errors within the diagnostic window"

if compgen -G '/var/log/apache2/error.log*' >/dev/null; then
    sudo zgrep \
        -hF "$APACHE_ERROR_DAY" \
        /var/log/apache2/error.log* \
        2>/dev/null |
    tail -1000

    echo
    echo "Key PHP/Apache errors:"

    sudo zgrep \
        -hEi \
        'PHP Fatal|PHP Parse|Uncaught|Allowed memory|Maximum execution|segmentation|segfault|permission denied|client intended to send too large body|AH[0-9]{5}|proxy:error|rewrite:error' \
        /var/log/apache2/error.log* \
        2>/dev/null |
    tail -1000
else
    echo "No /var/log/apache2/error.log* files found"
fi

section "Apache access.log: abnormal HTTP status codes"

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
    echo "Abnormal status-code counts:"

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
    echo "Paths with the most 5xx requests:"

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
    echo "No /var/log/apache2/access.log* files found"
fi

section "System package update history"

if compgen -G '/var/log/dpkg.log*' >/dev/null; then
    sudo zgrep \
        -hE "^(${START_DATE}|${END_DATE}) .* (install|upgrade|remove) " \
        /var/log/dpkg.log* \
        2>/dev/null |
    tail -500
fi

echo
echo "Automatic upgrade service logs:"

if systemctl list-unit-files --type=service 2>/dev/null |
    awk '{print $1}' |
    grep -qx 'unattended-upgrades.service'; then

    sudo journalctl \
        -u unattended-upgrades \
        --since "$SINCE" \
        --until "$UNTIL" \
        --no-pager
else
    echo "unattended-upgrades.service not found."
fi

section "Live HTTP requests"

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
        -w 'Site URL: HTTP=%{http_code} DNS=%{time_namelookup}s connect=%{time_connect}s start=%{time_starttransfer}s total=%{time_total}s final=%{url_effective}\n' \
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
    echo "Cannot run the site URL test."
fi

section "Automated diagnostic findings"

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

printf 'OOM-related entries: %s\n' "$OOM_COUNT"
printf 'Kernel crash entries: %s\n' "$SEGFAULT_COUNT"
printf 'Current failed systemd units: %s\n' "$FAILED_COUNT"
printf 'Core files changed within the window: %s\n' "$CORE_CHANGED"
printf 'Plugin, MU plugin, or theme files changed within the window: %s\n' "$CONTENT_CHANGED"
printf 'Apache 4xx responses today: %s\n' "$HTTP_4XX"
printf 'Apache 5xx responses today: %s\n' "$HTTP_5XX"

echo

if (( OOM_COUNT > 0 )); then
    echo "[HIGH PRIORITY] OOM or killed-process entries found. Check memory and swap first."
fi

if (( SEGFAULT_COUNT > 0 )); then
    echo "[HIGH PRIORITY] Process crashes found. Use kernel logs to identify the process."
fi

if (( HTTP_5XX > 0 )); then
    echo "[HIGH PRIORITY] Apache 5xx responses found. Inspect the paths and error.log."
fi

if (( CORE_CHANGED > 0 )); then
    echo "[FINDING] Core files changed during the window; an update or overwrite may have occurred."
else
    echo "[NEGATIVE FINDING] No core-file changes found during the window."
fi

if (( CONTENT_CHANGED > 0 )); then
    echo "[FINDING] Plugins, MU plugins, or themes changed during the window."
else
    echo "[NEGATIVE FINDING] No plugin, MU plugin, or theme changes found during the window."
fi

if ((
    OOM_COUNT == 0 &&
    SEGFAULT_COUNT == 0 &&
    HTTP_5XX == 0 &&
    CORE_CHANGED == 0 &&
    CONTENT_CHANGED == 0
)); then
    echo "[NOTE] No obvious update, OOM, crash, or 5xx findings. Inspect caching, 4xx responses, service restarts, and individual requests."
fi

section "Done"

echo "Report saved: $REPORT"
echo "The script did not modify WordPress, the database, caches, or service configuration."

sudo chown \
    "$REAL_USER":"$(id -gn "$REAL_USER")" \
    "$REPORT" \
    2>/dev/null ||
true
