# Historical Anki PDF to WordPress

Use the timestamp in an anki-stats-YYYY-MM-DD@HH-MM-SS.pdf filename to create or reuse WordPress posts and attachments, with timestamp readback.

## Availability

- Category: Anki and study
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run anki-time-travel.sh --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Import historical Anki PDF into WordPress

Creates or reuses WordPress posts and attachments. The filename must include a timestamp.

Confirmation level: high.

- Historical statistics PDF: file; required

## Requirements and effects

Requires WP-CLI and the configured local WordPress installation. PDF filenames must follow anki-stats-YYYY-MM-DD@HH-MM-SS.pdf. Writes posts and attachments, sets historical timestamps, then verifies dates, media paths, parent linkage, category and tag.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
