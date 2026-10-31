# Process WeChat export HTML restrictions

Process conversations/*/messages.html and generate messages-unlocked.html by removing recognized integrity checks and hidden elements.

## Availability

- Category: Files and archives
- Status: Available; real-system acceptance pending
- Risk: medium

## Command line

```bash
mint-toolbox --run unlock_wechat_export --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Generate readable chat HTML

Generates messages-unlocked.html under conversations without overwriting existing files.

Confirmation level: medium.

- WeChat export root folder: folder; required

## Requirements and effects

Generates conversations/*/messages-unlocked.html from messages.html. Existing output is skipped unless --overwrite is supplied. Review generated content before publishing.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
