# Import WeChat exports into WordPress

Synchronize exported assets to WordPress uploads and create or update posts embedding messages-unlocked.html. Contains private chat data.

## Availability

- Category: WordPress
- Status: Available; real-system acceptance pending
- Risk: high

## Command line

```bash
mint-toolbox --run import_wechat_export --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Preview import

The script may generate unlocked HTML before its dry-run checks. Preview can write files.

Confirmation level: medium.

- WeChat export root folder: folder; required

### Import WeChat records into WordPress

Copies exported assets and creates or updates WordPress posts containing private chats.

Confirmation level: high.

- WeChat export root folder: folder; required

## Requirements and effects

Contains private chat information. Requires WP-CLI and the configured WordPress upload directory. Preview may generate unlocked HTML before checking planned imports. Existing WordPress post-title prefixes are retained for compatibility; this does not rename existing posts.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
