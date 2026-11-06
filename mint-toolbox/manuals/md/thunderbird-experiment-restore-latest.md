# Restore latest Thunderbird experiment backup

Restore a TaskFix profile from the latest before-experiment backup after backing up the current profile. Requires YES confirmation.

## Availability

- Category: CalDAV and Thunderbird
- Status: Available; real-system acceptance pending
- Risk: critical

## Command line

```bash
mint-toolbox --run thunderbird-experiment-restore-latest --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Restore the latest experimental backup

Replaces a Thunderbird profile. Close Thunderbird first. The script also requires YES confirmation.

Confirmation level: critical.


## Requirements and effects

This entry uses the machine-specific executable or profile paths from the original script. Verify those paths and close conflicting applications before running it. Restoring a profile replaces live data; the script requires explicit confirmation.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
