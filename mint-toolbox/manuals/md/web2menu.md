# Website application-menu entry

Fetch a website title and favicon and create a Linux Mint/Cinnamon desktop menu entry for the URL.

## Availability

- Category: Desktop and launchers
- Status: Available; real-system acceptance pending
- Risk: medium

## Command line

```bash
mint-toolbox --run web2menu --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Add a website to the application menu

Creates a Linux Mint/Cinnamon desktop application entry.

Confirmation level: medium.

- Website URL: text; required
- Display name (optional): text; optional

## Requirements and effects

Accepts HTTP/HTTPS URLs. Writes a desktop entry and downloaded icon to the current user application directories. The displayed website title is external content.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
