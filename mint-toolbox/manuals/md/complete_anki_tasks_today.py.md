# Complete matching Anki CalDAV tasks

Find incomplete VTODOs due on the specified date whose titles match a keyword, then complete them in bulk.

## Availability

- Category: CalDAV and Thunderbird
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run complete_anki_tasks_today.py --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Preview matching CalDAV tasks

Review the preview before applying changes.

Confirmation level: low.

- Title keyword: text; required; default: Anki
- Target date YYYY-MM-DD (optional): text; optional

### Complete matching tasks in bulk

Changes task completion status on the CalDAV server.

Confirmation level: high.

- Title keyword: text; required; default: Anki
- Target date YYYY-MM-DD (optional): text; optional

## Requirements and effects

Uses its own Python virtual environment and may install or repair CalDAV dependencies on first use. Supply credentials through CALDAV_PASSWORD or its interactive password prompt. Review --dry-run before completing tasks.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
