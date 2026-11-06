# WordPress read-only diagnostics

Collect system logs, service status, recently modified file metadata and HTTP checks into a text diagnostic report.

## Availability

- Category: WordPress
- Status: Available; real-system acceptance pending
- Risk: medium

## Command line

```bash
mint-toolbox --run wordpress_diagnose_today.sh --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Generate a WordPress diagnostic report

Runs the read-only diagnostic script and saves the report to the selected folder.

Confirmation level: low.

- Report output folder: folder; optional

## Requirements and effects

Requires a local WordPress installation and WP-CLI. Uses sudo for read-only system diagnostics. Options include --wp-path, --web-user, --since, --until and --output-dir. Reports may contain private host and site metadata.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
