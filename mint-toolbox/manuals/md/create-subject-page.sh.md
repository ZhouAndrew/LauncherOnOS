# WordPress subject index pages

Create or update subject tags and child pages beneath the configured parent, including a Gutenberg Query Loop.

## Availability

- Category: WordPress
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run create-subject-page.sh --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Create or update subject pages

Creates or updates WordPress tags and subject pages using the configured parent page.

Confirmation level: high.

- Subject names (comma-separated): text; required

## Requirements and effects

Requires WP-CLI and the configured WordPress parent page. Creates or updates tags and subject pages. Subject names are user-provided content and are preserved as entered.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
