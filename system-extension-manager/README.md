# System Extension Manager

An independent manager for system extensions. Enable installs a bundled Debian package;
Disable uninstalls that package. The interface shows multiple real extensions and actual dpkg state.

## Install and open

```bash
sudo apt install ./system-extension-manager_0.1.0_all.deb
system-extension-manager
```

The application menu entry is **System Extension Manager**. Its desktop entry and CLI open the same manager.
The package contains this manager, its extension catalog, both extension debs and verified source recipes.
It does not require the abandoned toolbox application.

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
system-extension-manager --list
system-extension-manager --enable anki-time-travel
system-extension-manager --open anki-time-travel
system-extension-manager --disable anki-time-travel
system-extension-manager --build anki-time-travel
system-extension-manager --enable zip-trash
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

## Build and test

```bash
python3 system-extension-manager/build.py
xvfb-run -a python3 -m unittest discover -s system-extension-manager/tests -v
```
