#!/usr/bin/env bash
set -euo pipefail

# create-subject-page.sh
#
# Create/update WordPress subject index pages under a parent page.
# Each subject page automatically shows posts carrying a tag with the
# same name, using a Gutenberg Query Loop like the current "English" page.
#
# Examples:
#   ./create-subject-page.sh "Physics"
#   ./create-subject-page.sh English Math Physics Chemistry Biology
#
# Optional environment variables:
#   WP_PATH=/var/www/html/wordpress
#   PARENT_TITLE="My Project"
#   PER_PAGE=10
#   FORCE=0
#
# FORCE=1 allows the script to take over an existing child page that was
# not previously created/managed by this script.

WP_PATH="${WP_PATH:-/var/www/html/wordpress}"
PARENT_TITLE="${PARENT_TITLE:-My Project}"
PER_PAGE="${PER_PAGE:-10}"
FORCE="${FORCE:-0}"
GENERATOR_VERSION="v1"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

command -v wp >/dev/null 2>&1 || die "wp (WP-CLI) was not found in PATH."
[[ -d "$WP_PATH" ]] || die "WordPress path does not exist: $WP_PATH"

WP=(wp --path="$WP_PATH")

"${WP[@]}" core is-installed >/dev/null 2>&1 \
    || die "No working WordPress installation found at: $WP_PATH"

[[ "$PER_PAGE" =~ ^[1-9][0-9]*$ ]] \
    || die "PER_PAGE must be a positive integer."
[[ "$FORCE" == "0" || "$FORCE" == "1" ]] \
    || die "FORCE must be 0 or 1."

find_exact_pages() {
    local title="$1"
    local parent_id="${2:-}"
    local id actual_title
    local args=(post list --post_type=page --post_status=any --field=ID)

    if [[ -n "$parent_id" ]]; then
        args+=(--post_parent="$parent_id")
    fi

    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        actual_title="$("${WP[@]}" post get "$id" --field=post_title 2>/dev/null || true)"
        if [[ "$actual_title" == "$title" ]]; then
            printf '%s\n' "$id"
        fi
    done < <("${WP[@]}" "${args[@]}")
}

find_exact_tag_id() {
    local name="$1"
    local id actual_name

    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        actual_name="$("${WP[@]}" term get post_tag "$id" --field=name 2>/dev/null || true)"
        if [[ "$actual_name" == "$name" ]]; then
            printf '%s\n' "$id"
            return 0
        fi
    done < <("${WP[@]}" term list post_tag --search="$name" --field=term_id)

    return 1
}

build_query_content() {
    local tag_id="$1"

    cat <<EOF
<!-- wp:query {"queryId":17,"query":{"perPage":${PER_PAGE},"pages":0,"offset":0,"postType":"post","order":"desc","orderBy":"date","author":"","search":"","exclude":[],"sticky":"","inherit":false,"taxQuery":{"post_tag":[${tag_id}],"category":[]}},"metadata":{"categories":["posts"],"patternName":"core/query-standard-posts","name":"Standard"}} -->
<div class="wp-block-query"><!-- wp:post-template -->
<!-- wp:post-title {"isLink":true} /-->

<!-- wp:post-featured-image {"isLink":true,"align":"wide"} /-->

<!-- wp:post-excerpt /-->

<!-- wp:separator {"opacity":"css"} -->
<hr class="wp-block-separator has-css-opacity"/>
<!-- /wp:separator -->

<!-- wp:post-date {"metadata":{"bindings":{"datetime":{"source":"core/post-data","args":{"field":"date"}}}}} /-->
<!-- /wp:post-template --></div>
<!-- /wp:query -->

<!-- wp:paragraph -->
<p></p>
<!-- /wp:paragraph -->
EOF
}

# ---- Locate the parent page exactly ----
mapfile -t parent_ids < <(find_exact_pages "$PARENT_TITLE")

if (( ${#parent_ids[@]} == 0 )); then
    die "Parent page not found: \"$PARENT_TITLE\""
elif (( ${#parent_ids[@]} > 1 )); then
    printf 'ERROR: More than one page is titled "%s": %s\n' \
        "$PARENT_TITLE" "${parent_ids[*]}" >&2
    printf 'Rename duplicates or change PARENT_TITLE before running this script.\n' >&2
    exit 1
fi

parent_id="${parent_ids[0]}"
printf 'Parent: %s (ID=%s)\n' "$PARENT_TITLE" "$parent_id"

if (( $# == 0 )); then
    printf '\nUsage:\n'
    printf '  %s "Physics"\n' "$0"
    printf '  %s English Math Physics Chemistry Biology\n' "$0"
    exit 2
fi

created=0
updated=0
unchanged=0
skipped=0
failed=0

for subject in "$@"; do
    printf '\n=== %s ===\n' "$subject"

    if [[ -z "${subject//[[:space:]]/}" ]]; then
        printf 'SKIP: empty subject name.\n'
        ((skipped++)) || true
        continue
    fi

    # ---- Find/create matching post tag ----
    tag_id="$(find_exact_tag_id "$subject" || true)"

    if [[ -z "$tag_id" ]]; then
        if ! tag_id="$("${WP[@]}" term create post_tag "$subject" --porcelain)"; then
            printf 'ERROR: Could not create tag "%s".\n' "$subject" >&2
            ((failed++)) || true
            continue
        fi
        printf 'Tag: created "%s" (ID=%s)\n' "$subject" "$tag_id"
    else
        printf 'Tag: exists "%s" (ID=%s)\n' "$subject" "$tag_id"
    fi

    content="$(build_query_content "$tag_id")"

    # ---- Find exact child page under My Project ----
    mapfile -t page_ids < <(find_exact_pages "$subject" "$parent_id")

    if (( ${#page_ids[@]} > 1 )); then
        printf 'ERROR: More than one child page named "%s" exists under "%s": %s\n' \
            "$subject" "$PARENT_TITLE" "${page_ids[*]}" >&2
        ((failed++)) || true
        continue
    fi

    if (( ${#page_ids[@]} == 0 )); then
        # Prevent silently creating a second same-title page elsewhere.
        mapfile -t same_title_anywhere < <(find_exact_pages "$subject")
        if (( ${#same_title_anywhere[@]} > 0 )); then
            printf 'SKIP: a page titled "%s" already exists elsewhere (ID=%s).\n' \
                "$subject" "${same_title_anywhere[*]}"
            printf '      It was NOT re-parented automatically.\n'
            ((skipped++)) || true
            continue
        fi

        if ! page_id="$("${WP[@]}" post create \
            --post_type=page \
            --post_status=publish \
            --post_title="$subject" \
            --post_parent="$parent_id" \
            --post_content="$content" \
            --porcelain)"; then
            printf 'ERROR: Could not create page "%s".\n' "$subject" >&2
            ((failed++)) || true
            continue
        fi

        "${WP[@]}" post meta update "$page_id" _subject_index_generator "$GENERATOR_VERSION" >/dev/null
        "${WP[@]}" post meta update "$page_id" _subject_index_subject "$subject" >/dev/null
        "${WP[@]}" post meta update "$page_id" _subject_index_tag_id "$tag_id" >/dev/null

        slug="$("${WP[@]}" post get "$page_id" --field=post_name)"
        printf 'Page: created "%s" (ID=%s, slug=%s)\n' "$subject" "$page_id" "$slug"
        printf 'Query: posts tagged "%s" (tag ID=%s), newest first, %s per page\n' \
            "$subject" "$tag_id" "$PER_PAGE"
        ((created++)) || true
        continue
    fi

    page_id="${page_ids[0]}"
    managed_by="$("${WP[@]}" post meta get "$page_id" _subject_index_generator 2>/dev/null || true)"
    current_content="$("${WP[@]}" post get "$page_id" --field=post_content)"

    if [[ "$current_content" == "$content" ]]; then
        # Adopt exact matching legacy pages without changing their visible content.
        "${WP[@]}" post meta update "$page_id" _subject_index_generator "$GENERATOR_VERSION" >/dev/null
        "${WP[@]}" post meta update "$page_id" _subject_index_subject "$subject" >/dev/null
        "${WP[@]}" post meta update "$page_id" _subject_index_tag_id "$tag_id" >/dev/null
        printf 'Page: already correct (ID=%s). No visible change.\n' "$page_id"
        ((unchanged++)) || true
        continue
    fi

    if [[ "$managed_by" == "$GENERATOR_VERSION" || "$FORCE" == "1" ]]; then
        "${WP[@]}" post update "$page_id" \
            --post_parent="$parent_id" \
            --post_status=publish \
            --post_content="$content" >/dev/null

        "${WP[@]}" post meta update "$page_id" _subject_index_generator "$GENERATOR_VERSION" >/dev/null
        "${WP[@]}" post meta update "$page_id" _subject_index_subject "$subject" >/dev/null
        "${WP[@]}" post meta update "$page_id" _subject_index_tag_id "$tag_id" >/dev/null

        printf 'Page: updated "%s" (ID=%s)\n' "$subject" "$page_id"
        ((updated++)) || true
    else
        printf 'SKIP: "%s" already exists under "%s" (ID=%s), but is not managed by this script.\n' \
            "$subject" "$PARENT_TITLE" "$page_id"
        printf '      Nothing was overwritten.\n'
        printf '      To replace its content with the generated Query Loop, run:\n'
        printf '      FORCE=1 %q %q\n' "$0" "$subject"
        ((skipped++)) || true
    fi
done

printf '\n=== Summary ===\n'
printf 'Created   : %d\n' "$created"
printf 'Updated   : %d\n' "$updated"
printf 'Unchanged : %d\n' "$unchanged"
printf 'Skipped   : %d\n' "$skipped"
printf 'Failed    : %d\n' "$failed"

if (( failed > 0 )); then
    exit 1
fi
