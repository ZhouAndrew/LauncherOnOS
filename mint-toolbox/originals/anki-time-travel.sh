#!/usr/bin/env bash
set -Eeuo pipefail

# Anki historical stats PDF "time-travel" backfill helper
#
# Usage:
#   ./anki-time-travel.sh /path/to/anki-stats-2026-09-27@15-20-32.pdf
#
# Optional:
#   WP_PATH=/var/www/html/wordpress ./anki-time-travel.sh /path/to/file.pdf
#
# What it does:
#   - parses historical date/time from the PDF filename
#   - validates that the date/time really exists
#   - creates/reuses a matching WordPress post
#   - imports/reuses the PDF under the historical YYYY/MM uploads path
#   - embeds it using the Gutenberg File block
#   - sets Category=Anki and Tag=Anki
#   - links attachment.post_parent to the post
#   - locks post/attachment date + modified timestamps to the historical time
#   - performs final verification
#
# Expected filename:
#   anki-stats-YYYY-MM-DD@HH-MM-SS.pdf

WP_PATH="${WP_PATH:-/var/www/html/wordpress}"

die() {
    printf '✗ %s\n' "$*" >&2
    exit 1
}

info() {
    printf '→ %s\n' "$*"
}

ok() {
    printf '✓ %s\n' "$*"
}

cleanup_dirs=()
cleanup() {
    local d
    for d in "${cleanup_dirs[@]:-}"; do
        [ -n "$d" ] && [ -d "$d" ] && rm -rf -- "$d"
    done
}
trap cleanup EXIT
trap 'printf "\n✗ 脚本在第 %s 行失败。\n" "$LINENO" >&2' ERR

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "找不到命令：$1"
}

sql_escape() {
    # SQL single-quote escaping for values we generated from trusted filenames.
    printf "%s" "$1" | sed "s/'/''/g"
}

if [ "$#" -lt 1 ]; then
    cat >&2 <<'EOF'
用法：
  anki-time-travel.sh /path/to/anki-stats-YYYY-MM-DD@HH-MM-SS.pdf

也可以一次传入多个 PDF：
  anki-time-travel.sh file1.pdf file2.pdf
EOF
    exit 2
fi

need_cmd wp
need_cmd date
need_cmd sed
need_cmd basename
need_cmd mktemp
need_cmd cp
need_cmd touch

[ -d "$WP_PATH" ] || die "找不到 WordPress 目录：$WP_PATH"
[ -f "$WP_PATH/wp-config.php" ] || die "这里不像 WordPress 根目录：$WP_PATH"

cd "$WP_PATH"

wp core is-installed >/dev/null 2>&1 || die "WP-CLI 无法确认此站点已安装。"
PREFIX="$(wp db prefix)"
[ -n "$PREFIX" ] || die "无法取得 WordPress 数据表前缀。"

ensure_term() {
    local taxonomy="$1"
    local name="$2"
    local slug="$3"

    if wp term get "$taxonomy" "$slug" --by=slug >/dev/null 2>&1; then
        return 0
    fi

    wp term create "$taxonomy" "$name" --slug="$slug" >/dev/null
}

ensure_term category "Anki" "anki"
ensure_term post_tag "Anki" "anki"

process_one() {
    local PDF="$1"
    [ -f "$PDF" ] || die "找不到 PDF：$PDF"

    local BASE
    BASE="$(basename -- "$PDF")"

    if [[ ! "$BASE" =~ ^anki-stats-([0-9]{4})-([0-9]{2})-([0-9]{2})@([0-9]{2})-([0-9]{2})-([0-9]{2})\.pdf$ ]]; then
        die "文件名格式不正确：$BASE
要求：anki-stats-YYYY-MM-DD@HH-MM-SS.pdf"
    fi

    local Y="${BASH_REMATCH[1]}"
    local M="${BASH_REMATCH[2]}"
    local D="${BASH_REMATCH[3]}"
    local HH="${BASH_REMATCH[4]}"
    local MI="${BASH_REMATCH[5]}"
    local SS="${BASH_REMATCH[6]}"

    local POST_DATE="$Y-$M-$D $HH:$MI:$SS"

    # Strict validation: GNU date may normalize invalid dates, so compare round-trip.
    local ROUNDTRIP
    ROUNDTRIP="$(LC_ALL=C date -d "$POST_DATE" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || true)"
    [ "$ROUNDTRIP" = "$POST_DATE" ] || die "文件名中的日期/时间无效：$POST_DATE"

    local HUMAN
    HUMAN="$(LC_ALL=C date -d "$POST_DATE" '+%B %-d %Y %A')"
    local TITLE="Anki at $HUMAN"
    local EXPECTED_MEDIA="$Y/$M/$BASE"
    local MEDIA_TITLE="${BASE%.pdf}"

    # Let WordPress calculate GMT using the site's own timezone configuration.
    local POST_GMT
    POST_GMT="$(wp eval 'echo get_gmt_from_date($args[0]);' "$POST_DATE")"
    [ -n "$POST_GMT" ] || die "无法让 WordPress 计算 GMT：$POST_DATE"

    local TITLE_SQL POST_DATE_SQL EXPECTED_MEDIA_SQL
    TITLE_SQL="$(sql_escape "$TITLE")"
    POST_DATE_SQL="$(sql_escape "$POST_DATE")"
    EXPECTED_MEDIA_SQL="$(sql_escape "$EXPECTED_MEDIA")"

    printf '\n============================================================\n'
    printf ' Anki 历史统计补档\n'
    printf '============================================================\n'
    printf 'PDF:        %s\n' "$PDF"
    printf '历史时间:   %s\n' "$POST_DATE"
    printf 'GMT:        %s\n' "$POST_GMT"
    printf '文章标题:   %s\n' "$TITLE"
    printf '目标路径:   %s\n' "$EXPECTED_MEDIA"
    printf '\n'

    info "查找或创建历史文章"

    local POST_ID
    POST_ID="$(
        wp db query "
            SELECT ID
            FROM ${PREFIX}posts
            WHERE post_type='post'
              AND post_title='${TITLE_SQL}'
              AND post_date='${POST_DATE_SQL}'
            ORDER BY ID DESC
            LIMIT 1;
        " --skip-column-names --silent 2>/dev/null | tr -d '[:space:]'
    )"

    if [ -n "$POST_ID" ]; then
        ok "复用已有文章 ID=$POST_ID"
    else
        POST_ID="$(
            wp post create \
                --post_type=post \
                --post_status=draft \
                --post_title="$TITLE" \
                --post_date="$POST_DATE" \
                --post_date_gmt="$POST_GMT" \
                --porcelain
        )"
        ok "创建文章 ID=$POST_ID"
    fi

    info "查找或导入历史 PDF 附件"

    local ATTACH_ID
    ATTACH_ID="$(
        wp db query "
            SELECT pm.post_id
            FROM ${PREFIX}postmeta pm
            INNER JOIN ${PREFIX}posts p ON p.ID=pm.post_id
            WHERE p.post_type='attachment'
              AND pm.meta_key='_wp_attached_file'
              AND pm.meta_value='${EXPECTED_MEDIA_SQL}'
            ORDER BY pm.post_id DESC
            LIMIT 1;
        " --skip-column-names --silent 2>/dev/null | tr -d '[:space:]'
    )"

    if [ -n "$ATTACH_ID" ]; then
        ok "复用已有附件 ID=$ATTACH_ID"
    else
        local TMPDIR
        TMPDIR="$(mktemp -d)"
        cleanup_dirs+=("$TMPDIR")

        cp -- "$PDF" "$TMPDIR/$BASE"
        touch -d "$POST_DATE" "$TMPDIR/$BASE"

        ATTACH_ID="$(
            wp media import "$TMPDIR/$BASE" \
                --post_id="$POST_ID" \
                --title="$MEDIA_TITLE" \
                --preserve-filetime \
                --porcelain
        )"

        ok "导入附件 ID=$ATTACH_ID"
    fi

    [ -n "$ATTACH_ID" ] || die "没有取得附件 ID。"

    wp post update "$ATTACH_ID" --post_parent="$POST_ID" >/dev/null

    local MEDIA_PATH PDF_URL
    MEDIA_PATH="$(wp post meta get "$ATTACH_ID" _wp_attached_file)"
    PDF_URL="$(wp post get "$ATTACH_ID" --field=guid)"

    [ -n "$PDF_URL" ] || die "无法取得附件 URL。"

    if [ "$MEDIA_PATH" != "$EXPECTED_MEDIA" ]; then
        die "附件路径不符合历史日期，停止：
实际：$MEDIA_PATH
预期：$EXPECTED_MEDIA"
    fi

    info "写入 Gutenberg PDF File block"

    local CONTENT
    CONTENT="$(cat <<EOF
<!-- wp:file {"id":$ATTACH_ID,"href":"$PDF_URL","displayPreview":true} -->
<div class="wp-block-file"><object class="wp-block-file__embed" data="$PDF_URL" type="application/pdf" style="width:100%;height:600px" aria-label="$BASE"></object><a href="$PDF_URL">$BASE</a><a href="$PDF_URL" class="wp-block-file__button wp-element-button" download>Download</a></div>
<!-- /wp:file -->
EOF
)"

    wp post update "$POST_ID" \
        --post_title="$TITLE" \
        --post_content="$CONTENT" \
        --post_status=publish >/dev/null

    wp post term set "$POST_ID" category anki --by=slug >/dev/null
    wp post term set "$POST_ID" post_tag anki --by=slug >/dev/null

    info "锁定文章与附件的历史时间"

    wp db query "
        UPDATE ${PREFIX}posts
        SET
            post_date='${POST_DATE_SQL}',
            post_date_gmt='$(sql_escape "$POST_GMT")',
            post_modified='${POST_DATE_SQL}',
            post_modified_gmt='$(sql_escape "$POST_GMT")'
        WHERE ID=${POST_ID};

        UPDATE ${PREFIX}posts
        SET
            post_parent=${POST_ID},
            post_date='${POST_DATE_SQL}',
            post_date_gmt='$(sql_escape "$POST_GMT")',
            post_modified='${POST_DATE_SQL}',
            post_modified_gmt='$(sql_escape "$POST_GMT")'
        WHERE ID=${ATTACH_ID};
    " >/dev/null

    wp cache flush >/dev/null 2>&1 || true

    info "最终验收"

    local ACTUAL_PARENT ACTUAL_POST_DATE ACTUAL_ATTACH_DATE ACTUAL_PATH
    local CAT TAG STATUS

    STATUS="$(wp post get "$POST_ID" --field=post_status)"
    ACTUAL_POST_DATE="$(wp post get "$POST_ID" --field=post_date)"
    ACTUAL_ATTACH_DATE="$(wp post get "$ATTACH_ID" --field=post_date)"
    ACTUAL_PARENT="$(wp post get "$ATTACH_ID" --field=post_parent)"
    ACTUAL_PATH="$(wp post meta get "$ATTACH_ID" _wp_attached_file)"
    CAT="$(wp post term list "$POST_ID" category --field=slug | tr '\n' ' ')"
    TAG="$(wp post term list "$POST_ID" post_tag --field=slug | tr '\n' ' ')"

    [ "$STATUS" = "publish" ] || die "验收失败：文章不是 publish。"
    [ "$ACTUAL_POST_DATE" = "$POST_DATE" ] || die "验收失败：文章历史时间不正确。"
    [ "$ACTUAL_ATTACH_DATE" = "$POST_DATE" ] || die "验收失败：附件历史时间不正确。"
    [ "$ACTUAL_PARENT" = "$POST_ID" ] || die "验收失败：attachment.post_parent 不正确。"
    [ "$ACTUAL_PATH" = "$EXPECTED_MEDIA" ] || die "验收失败：附件历史路径不正确。"
    [[ " $CAT " == *" anki "* ]] || die "验收失败：Category=Anki 不存在。"
    [[ " $TAG " == *" anki "* ]] || die "验收失败：Tag=Anki 不存在。"

    ok "验收通过"

    printf '\n文章 ID:     %s\n' "$POST_ID"
    printf '附件 ID:     %s\n' "$ATTACH_ID"
    printf '文章 URL:    %s\n' "$(wp post url "$POST_ID")"
    printf '媒体路径:    %s\n' "$ACTUAL_PATH"
    printf 'Category:    Anki\n'
    printf 'Tag:         Anki\n'
    printf '历史时间:    %s\n' "$POST_DATE"
    printf '============================================================\n'
}

for pdf in "$@"; do
    process_one "$pdf"
done
