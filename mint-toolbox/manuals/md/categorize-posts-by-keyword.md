# WordPress categories by keyword

Preview matching post titles, excerpts and content, then append a category and read the result back.

## Availability

- Category: WordPress
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run categorize-posts-by-keyword --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Preview matching posts

Search only; categories are not changed.

Confirmation level: low.

- Search keyword: text; required

### Set post categories in bulk

Changes categories on all matching posts. Preview the matches first.

Confirmation level: high.

- Search keyword: text; required
- Category name: text; required

## Requirements and effects

Requires WP-CLI and access to the configured WordPress site. Start with --dry-run. The --yes operation changes matching post categories and verifies the result.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
