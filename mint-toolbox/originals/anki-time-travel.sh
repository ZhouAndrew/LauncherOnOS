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
#   anki-stats-YYYY-MM-DD@HH-MM-SS.pdf (optional numeric download suffix, e.g. -1)

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
    return 0
}
trap cleanup EXIT
trap 'printf "\n✗ Script failed at line %s.\n" "$LINENO" >&2' ERR

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Command not found: $1"
}

sql_escape() {
    # SQL single-quote escaping for values we generated from trusted filenames.
    printf "%s" "$1" | sed "s/'/''/g"
}

if [ "$#" -lt 1 ]; then
    cat >&2 <<'EOF'
Usage:
  anki-time-travel.sh /path/to/anki-stats-YYYY-MM-DD@HH-MM-SS.pdf

Multiple PDF files can be provided:
  anki-time-travel.sh file1.pdf file2.pdf
EOF
    exit 2
fi

# Resolve every input against the launch directory before changing to WP_PATH.
# Preflight all inputs before any WordPress command can run.
CALLER_DIR="$PWD"
PDF_NAME_RE='^anki-stats-([0-9]{4})-([0-9]{2})-([0-9]{2})@([0-9]{2})-([0-9]{2})-([0-9]{2})(-[0-9]+)?\.pdf$'
pdf_inputs=()
for input in "$@"; do
    if [[ "$input" != /* ]]; then
        input="$CALLER_DIR/$input"
    fi
    [ -f "$input" ] || die "PDF not found: $input"
    base="${input##*/}"
    if [[ ! "$base" =~ $PDF_NAME_RE ]]; then
        die "Invalid filename format: $base
Required: anki-stats-YYYY-MM-DD@HH-MM-SS.pdf (optional numeric suffix, e.g. -1)"
    fi
    pdf_inputs+=("$input")
done

need_cmd wp
need_cmd date
need_cmd sed
need_cmd basename
need_cmd mktemp
need_cmd cp
need_cmd touch

[ -d "$WP_PATH" ] || die "WordPress directory not found: $WP_PATH"
[ -f "$WP_PATH/wp-config.php" ] || die "Not a WordPress root directory: $WP_PATH"

cd "$WP_PATH"

wp core is-installed >/dev/null 2>&1 || die "WP-CLI could not verify that the site is installed."
PREFIX="$(wp db prefix)"
[ -n "$PREFIX" ] || die "Cannot read the WordPress database table prefix."

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
    [ -f "$PDF" ] || die "PDF not found: $PDF"

    local BASE
    BASE="$(basename -- "$PDF")"

    if [[ ! "$BASE" =~ $PDF_NAME_RE ]]; then
        die "Invalid filename format: $BASE
Required: anki-stats-YYYY-MM-DD@HH-MM-SS.pdf (optional numeric suffix, e.g. -1)"
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
    [ "$ROUNDTRIP" = "$POST_DATE" ] || die "Invalid filename timestamp: $POST_DATE"

    local HUMAN
    HUMAN="$(LC_ALL=C date -d "$POST_DATE" '+%B %-d %Y %A')"
    local TITLE="Anki at $HUMAN"
    local EXPECTED_MEDIA="$Y/$M/$BASE"
    local MEDIA_TITLE="${BASE%.pdf}"

    # Let WordPress calculate GMT using the site's own timezone configuration.
    local POST_GMT
    POST_GMT="$(wp eval 'echo get_gmt_from_date($args[0]);' "$POST_DATE")"
    [ -n "$POST_GMT" ] || die "WordPress could not calculate GMT: $POST_DATE"

    local TITLE_SQL POST_DATE_SQL EXPECTED_MEDIA_SQL
    TITLE_SQL="$(sql_escape "$TITLE")"
    POST_DATE_SQL="$(sql_escape "$POST_DATE")"
    EXPECTED_MEDIA_SQL="$(sql_escape "$EXPECTED_MEDIA")"

    printf '\n============================================================\n'
    printf ' Historical Anki statistics import\n'
    printf '============================================================\n'
    printf 'PDF:        %s\n' "$PDF"
    printf 'Historical timestamp:   %s\n' "$POST_DATE"
    printf 'GMT:        %s\n' "$POST_GMT"
    printf 'Post title:   %s\n' "$TITLE"
    printf 'Target path:   %s\n' "$EXPECTED_MEDIA"
    printf '\n'

    info "Finding or creating a historical post"

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
        ok "Reusing existing post ID=$POST_ID"
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
        ok "Created post ID=$POST_ID"
    fi

    info "Finding or importing a historical PDF attachment"

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
        ok "Reusing attachment ID=$ATTACH_ID"
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

        ok "Imported attachment ID=$ATTACH_ID"
    fi

    [ -n "$ATTACH_ID" ] || die "No attachment ID was returned."

    wp post update "$ATTACH_ID" --post_parent="$POST_ID" >/dev/null

    local MEDIA_PATH PDF_URL
    MEDIA_PATH="$(wp post meta get "$ATTACH_ID" _wp_attached_file)"
    PDF_URL="$(wp post get "$ATTACH_ID" --field=guid)"

    [ -n "$PDF_URL" ] || die "Cannot read the attachment URL."

    if [ "$MEDIA_PATH" != "$EXPECTED_MEDIA" ]; then
        die "Attachment path does not match the historical date; stopping:
Actual: $MEDIA_PATH
Expected: $EXPECTED_MEDIA"
    fi

    info "Writing Gutenberg PDF File block"

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

    info "Setting historical timestamps on the post and attachment"

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

    info "Final verification"

    local ACTUAL_PARENT ACTUAL_POST_DATE ACTUAL_ATTACH_DATE ACTUAL_PATH
    local CAT TAG STATUS

    STATUS="$(wp post get "$POST_ID" --field=post_status)"
    ACTUAL_POST_DATE="$(wp post get "$POST_ID" --field=post_date)"
    ACTUAL_ATTACH_DATE="$(wp post get "$ATTACH_ID" --field=post_date)"
    ACTUAL_PARENT="$(wp post get "$ATTACH_ID" --field=post_parent)"
    ACTUAL_PATH="$(wp post meta get "$ATTACH_ID" _wp_attached_file)"
    CAT="$(wp post term list "$POST_ID" category --field=slug | tr '\n' ' ')"
    TAG="$(wp post term list "$POST_ID" post_tag --field=slug | tr '\n' ' ')"

    [ "$STATUS" = "publish" ] || die "Verification failed: post is not published."
    [ "$ACTUAL_POST_DATE" = "$POST_DATE" ] || die "Verification failed: post timestamp mismatch."
    [ "$ACTUAL_ATTACH_DATE" = "$POST_DATE" ] || die "Verification failed: attachment timestamp mismatch."
    [ "$ACTUAL_PARENT" = "$POST_ID" ] || die "Verification failed: attachment.post_parent mismatch."
    [ "$ACTUAL_PATH" = "$EXPECTED_MEDIA" ] || die "Verification failed: attachment historical path mismatch."
    [[ " $CAT " == *" anki "* ]] || die "Verification failed: Category=Anki is missing."
    [[ " $TAG " == *" anki "* ]] || die "Verification failed: Tag=Anki is missing."

    ok "Verification passed"

    printf '\nPost ID:     %s\n' "$POST_ID"
    printf 'Attachment ID:     %s\n' "$ATTACH_ID"
    printf 'Post URL:    %s\n' "$(wp post url "$POST_ID")"
    printf 'Media path:    %s\n' "$ACTUAL_PATH"
    printf 'Category:    Anki\n'
    printf 'Tag:         Anki\n'
    printf 'Historical timestamp:    %s\n' "$POST_DATE"
    printf '============================================================\n'
}

for pdf in "${pdf_inputs[@]}"; do
    process_one "$pdf"
done
