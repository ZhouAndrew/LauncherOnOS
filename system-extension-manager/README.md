# System Extension Manager

An independent manager for system extensions. Enable installs a bundled Debian package;
Disable uninstalls that package. The interface shows multiple real extensions and actual dpkg state.

## Portable test release: 0.2.0-test2

Extract the source ZIP, open its folder and run as your desktop user:

```bash
bash run.sh
```

No manager installation or package build runs at startup. Requires Linux Mint / Debian,
Python 3.10+ and python3-tk for the desktop window. CLI listing does not require Tk.
The source folder can be moved; run.sh resolves its own location.

The manager includes three extension debs and pinned source recipes. Enabling or disabling
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
- **HomeBackUp**: Independent Borg recovery backup extension. Installs into the manager as a normal system package with status/readback and optional source build. After Enable, configure once from the Linux Mint applications menu using `homebackup-ext setup` or `homebackup-ext use-existing` (existing root-only Borg credentials). Reuses `/media/andrew/HomeBackUp/Mint-Recovery-Borg` without deleting existing backups on installation; monthly timer with at most three backup dates. Requires an existing Borg 1.x repo and the configured HomeBackUp disk; `/dev/sdc7` is not included. The extension's console menu is separate from the manager.
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
bash run.sh --enable homebackup
bash run.sh --build homebackup
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
Source builds require dpkg-deb and xz; ZIP and Trash requires Nemo, zip, unzip and GIO. HomeBackUp requires BorgBackup 1.x and a separately enrolled encryption passphrase. Package installation does not request a Borg password; use the extension setup command afterwards.
Anki Time Travel requires the existing WP-CLI and WordPress environment.

## State-aware actions

Installed older versions are shown as Enabled with Update available. Install and
source-install are disabled for installed extensions. Uninstall is disabled for absent
extensions. Update is a separate action (`bash run.sh --update ID`). All changes
recheck dpkg before execution and read the package state back afterward. Unknown
status disables package actions and displays the error.

File and folder selection prefers GTK FileChooserNative through the system Python
and python3-gi / GTK 3. If unavailable, it falls back to Tk. Cancellation performs
no action. These changes apply to manager packaging, log saving and Anki file selection.

## Distribution

The GitHub Actions `System Extension Manager` workflow builds a portable source ZIP **with all three bundled extension debs** and an optional System Extension Manager `.deb` for download as CI artifacts. In the manager select **HomeBackUp** and choose **Enable / Install**; the system package manager requests one administrator authorization for installation. Updating an already-installed extension uses **Update**, and removing a missing package is a no-op. The Borg encryption password is a separate credential needed only for first setup or repository access. No sensitive backup data or credentials are shipped. Reinstall-and-restore and live Mint GUI installation are not yet acceptance-tested.

For a raw Git checkout (rather than the CI-distributed source ZIP), run `python3 system-extension-manager/build.py --extensions-only` before `bash system-extension-manager/run.sh` so the locally built HomeBackUp extension package and catalog are available. CI releases include the ready-to-install manager and all three bundled extension packages.
