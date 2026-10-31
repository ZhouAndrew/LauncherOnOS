# Mint Toolbox v0.4.0

A GUI-first collection of Linux utilities with a Debian system extension manager.
Inspired by the organization of Microsoft PowerToys; not affiliated with Microsoft.

## Install and start

Unpack the complete distribution and run:

```bash
bash install-and-open.sh
```

Or install the toolbox and open its main window:

```bash
bash install.sh
python3 "$HOME/.local/share/mint-toolbox/toolbox.py" --gui
```

The GUI requires `python3-tk`. Native file selection prefers Zenity when available.
Install missing desktop components with `sudo apt install python3-tk zenity pkexec`.
Run the application as your normal user. Only package installation/removal requests administrator authorization.
An existing toolbox installation is backed up; user settings are retained.

## System extensions

Open **System extensions...** in the main window, or use `mint-toolbox --plugins`.
The manager displays multiple tools in a scrollable table with independent package states,
search and status filters. Select a row to install, remove, or build that tool from source.
Currently one real extension is bundled: **Compress to ZIP and delete**, for Nemo.

Every operation shows its full commands, live combined stdout/stderr, stage and exit code.
Logs remain visible when an operation ends and can be copied or saved.
Private logs are also saved automatically under `$XDG_STATE_HOME/mint-toolbox/logs`
(default `~/.local/state/mint-toolbox/logs`).

Source builds use checked, pinned local source files and run without administrator privileges.
Generated packages are verified before apt installs them. Rebuilding cannot fix unsupported
source code or incompatible dependencies automatically. See [SYSTEM_PLUGINS.md](SYSTEM_PLUGINS.md).

## Command line

```bash
mint-toolbox --list
mint-toolbox --all --list
mint-toolbox --info extract_pdf_images.py
mint-toolbox --run extract_pdf_images.py ~/Documents/sample.pdf --output ~/Pictures
mint-toolbox --tui
mint-toolbox --plugins
mint-toolbox --plugin-list
mint-toolbox --plugin-enable zip-trash
mint-toolbox --plugin-disable zip-trash
mint-toolbox --plugin-build zip-trash
```

Existing script arguments pass through unchanged after `--run TOOL`.
Disabling a user tool preserves its script and settings. Marking it as removed only changes its catalog visibility.
System extension toggles install/remove Debian packages and affect all users.

## Language and existing data

Owned interface text, diagnostics, help, comments and manuals use English.
User filenames, website titles, entered values and external content are displayed as supplied.
The legacy WeChat importer's existing WordPress post-title prefix remains unchanged to preserve existing data behavior.

## Validation

```bash
python3 packaging/build.py
python3 -m unittest discover -s tests -v
```

CI additionally runs GUI tests through Xvfb, real GIO Trash operations and a real source build as a regular user.
Linux Mint desktop acceptance is still required for pkexec prompts and Nemo menu integration.
