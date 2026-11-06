# Archive folder and move to Trash

Create a timestamped tar.gz archive, verify readability, then move the original folder to desktop Trash.

## Availability

- Category: Files and archives
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run archive-folder-to-trash --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Archive and move to Trash

Create and verify the archive, then move the original folder to Trash.

Confirmation level: high.

- Folder to archive: folder; required
- Archive output folder (optional): folder; optional

## Requirements and effects

Requires tar and a desktop Trash utility. Verifies the tar.gz before moving the original folder to Trash. The output directory must exist and must not be inside the source folder.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
