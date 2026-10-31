# Anki Time Travel

A system-installable CLI and desktop tool for importing historical Anki statistics PDFs into local WordPress.

## Install

```bash
sudo apt install ./anki-time-travel_0.1.1_all.deb
```

The package installs the `anki-time-travel` command and an **Anki Time Travel** application-menu entry.
Do not run the application itself with sudo. Your normal user must already have access to the configured WordPress site and WP-CLI.
The package does not install or reconfigure WordPress, database credentials, or WP-CLI.

## Terminal

```bash
anki-time-travel --check
anki-time-travel ~/Desktop/anki-stats-2026-10-27@22-58-46-1.pdf
anki-time-travel --wp-path /var/www/html/wordpress first.pdf second.pdf
anki-time-travel --choose
anki-time-travel --gui
```

`--choose` opens a desktop multi-file chooser and then runs the import in the terminal.
`--gui` opens the full desktop window. Running without paths in a graphical session also opens this window.
Without a graphical session, provide PDF paths directly.

The WordPress directory is selected in this order: `--wp-path`, `WP_PATH`, saved desktop settings, then `/var/www/html/wordpress`.
The GUI saves its selected WordPress directory under `$XDG_CONFIG_HOME/anki-time-travel/settings.json`.
`--check` checks local prerequisites only; it does not test database access or modify WordPress.

## Desktop

Launch **Anki Time Travel** from the application menu, select the WordPress root, add PDFs and click **Import to WordPress**.
The desktop entry also supports **Open With** for PDF files without changing the default PDF viewer.
The log displays the script command and live output, remains visible after completion, and can be copied or saved.
Logs are saved automatically under the shared Mint Toolbox operation-log directory (`~/.local/state/mint-toolbox/logs` by default).

Supported filenames are `anki-stats-YYYY-MM-DD@HH-MM-SS.pdf`, optionally followed by a numeric download suffix before `.pdf`, such as `-1`.
Relative paths are resolved before the script changes to the WordPress directory.

Import creates or reuses posts and PDF attachments, sets the historical date/modified values, category/tag and parent linkage,
embeds a Gutenberg PDF preview and verifies the final values. It does not delete the source PDF.

## Remove

```bash
sudo apt remove anki-time-travel
```

Removal does not delete imported WordPress content, source PDFs, user settings or logs.

## Build

From this repository checkout:

```bash
python3 anki-time-travel/build.py
```

The package uses the repository's tested Bash importer and shared log UI. No network download occurs during the build.
