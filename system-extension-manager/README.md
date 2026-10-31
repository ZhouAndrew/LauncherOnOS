# System Extension Manager

An independent manager for system extensions. Enable installs a bundled Debian package;
Disable uninstalls that package. The interface shows multiple real extensions and actual dpkg state.

## Portable test release: 0.2.0-test1

Extract the source ZIP, open its folder and run as your desktop user:

```bash
bash run.sh
```

No manager installation or package build runs at startup. Requires Linux Mint / Debian,
Python 3.10+ and python3-tk for the desktop window. CLI listing does not require Tk.
The source folder can be moved; run.sh resolves its own location.

The manager includes two extension debs and pinned source recipes. Enabling or disabling
an extension still uses the system package manager and requests administrator authorization.

## Optional manager package

Choose **Build Package...** in the source-running window and select an output folder.
Commands and build output appear in the live log. This creates a deb without installing it.
Alternatively:

```bash
bash run.sh --build-package --output-dir /tmp/manager-package
```

Only if you later want system installation, install that deb with apt.
The included system-extension-manager.desktop is for the optional installed manager.

## Extensions

- **ZIP and Trash**: Nemo context-menu ZIP creation, content verification and moving originals to Trash.
  Symbolic links are stored as links without following targets, including dangling and directory links.
- **Anki Time Travel**: CLI and desktop import of historical Anki PDFs into local WordPress.
  Relative paths, numeric download suffixes, GMT evaluation and exact-post permalink verification are included.
  Requires an existing accessible WordPress installation and WP-CLI. Installing or opening the application does not start an import.

Select Anki Time Travel, click **Enable / Install**, then **Open**.
An existing installed version is detected automatically. Enable upgrades it to the bundled version.
Disable removes the extension package without deleting WordPress posts, PDFs, settings or logs.
ZIP and Trash is used from Nemo's context menu and has no standalone application window.

## CLI

```bash
bash run.sh --list
bash run.sh --enable anki-time-travel
bash run.sh --open anki-time-travel
bash run.sh --disable anki-time-travel
bash run.sh --build anki-time-travel
bash run.sh --enable zip-trash
```

Full commands, live combined stdout/stderr, stages, exit codes and package-state readback appear in the log.
Logs remain visible and can be copied or saved. Automatic private logs use
`$XDG_STATE_HOME/system-extension-manager/logs`, default `~/.local/state/system-extension-manager/logs`.
Opening an extension keeps its execution log active until its window is closed.

Build from source verifies SHA-256-pinned bundled files and builds as the regular user in a fresh cache directory.
The generated deb is checked for package identity, version and architecture before apt dependency simulation and authorized installation.
Root builds are refused. Missing build tools are reported. This version does not download arbitrary source repositories
or automatically port incompatible source code.

Run the manager as your desktop user. Only installation/removal requests administrator authorization.
Installing/removing an extension affects all users. Removing the manager itself leaves independently installed extensions intact.

## Build extension packages and test

From this source folder:

```bash
python3 build.py --extensions-only
python3 -m unittest discover -s tests -v
```

GUI tests require a graphical session (or xvfb-run). Running build.py without arguments
prints help and builds nothing. Tests do not build the main manager deb.
Source builds require dpkg-deb and xz; ZIP and Trash requires Nemo, zip, unzip and GIO.
Anki Time Travel requires the existing WP-CLI and WordPress environment.
