# Thunderbird experiment: back up and launch

Check running Thunderbird processes, back up the experimental TaskFix profile, then launch the isolated experimental build.

## Availability

- Category: CalDAV and Thunderbird
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run thunderbird-experiment --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Back up and launch experimental build

Uses the existing isolated Thunderbird experimental environment.

Confirmation level: medium.


## Requirements and effects

This entry uses the machine-specific executable or profile paths from the original script. Verify those paths and close conflicting applications before running it. Restoring a profile replaces live data; the script requires explicit confirmation.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
