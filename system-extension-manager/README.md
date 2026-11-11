# System Extension Manager

**ACTIVE / MAINTAINED — 0.2.8.** An independent extension manager, not a front end for the retired application.
See [security status](../SECURITY_STATUS.md) for fixed and retained risks.
ZIP 0.4.5 keeps originals by default and rechecks each remaining input before opt-in Trash. HomeBackUp 0.1.6 uses guarded no-follow root locks and verifies service shutdown.
Anki 0.1.6 intentionally PUBLISHES: validated same-import updates may overwrite body,
categories and tags; conflicting same-path PDF bytes are blocked; PDFs may be
directly accessible. These are warned, not claimed fixed. Back up WordPress first.
Before upgrading HomeBackUp from 0.1.3, stop its timer and service; its old
maintenance scripts lack the new protections. The manager refuses unsafe upgrades.

Safety information is shown in a dismissible first-run dialog and acknowledged per
user at `$XDG_STATE_HOME/system-extension-manager/safety-notice-v1.ack`.
The main window has no permanent safety or retired-app banner. A Safety notes...
button lets users reopen the notes voluntarily. Risky package operations still
require explicit confirmation.

An independent manager for system extensions. Enable installs a bundled Debian package;
Disable uninstalls that package. The interface shows multiple real extensions and actual dpkg state.

## Security hardening in 0.2.8

- Privileged local Debian installation stages the approved package under root ownership, verifies the exact SHA-256 there, simulates APT and installs that same copy. The application's own package readback remains enforced.
- The portable manual Security Updates tool uses isolated Python (`-I`) and a root-owned SHA-256-verified source snapshot; it installs nothing without explicit user approval.
- HomeBackUp 0.1.6 uses no-follow root locks with owner/type/link and directory permission checks. Upgrade the independent package explicitly; the manager does not start any timer automatically.
- Link Provider 0.2.2 detects immediate nonzero exits and reports that process dispatch does not establish backend readiness.
- ZIP and Trash 0.4.5 checks each remaining input before moving it to Trash, checks its disappearance and reports partial moves; multi-file Trash is not atomic, and keeping originals remains the default.
- Anki Time Travel 0.1.6 retains publication but refuses unrelated WordPress title/date collisions and mismatched PDF attachment bytes.

**The changes in this Git repository do not upgrade existing installed extension packages.**
Review the new versions and explicitly use the manager's Update action. Actual
Linux Mint 22.x root APT, Borg retention/restore and live WordPress acceptance
remain separate. Do not upgrade the kernel/NVIDIA driver as part of this review.

## Portable test release: 0.2.8

Extract the source ZIP, open its folder and run as your desktop user:

```bash
bash run.sh
```

No manager installation or package build runs at startup. Requires Linux Mint / Debian,
Python 3.10+ and python3-tk for the desktop window. CLI listing does not require Tk.
The source folder can be moved; run.sh resolves its own location.

The manager includes **four installable extension debs** and one **portable Security Updates tool**.
Package extensions use administrator authorization for installation/removal. The Security Updates
tool never requires an extension installation.

## Optional manager package

Choose **Build Package...** in the source-running window and select an output folder.
Commands and build output appear in the live log. This creates a deb without installing it.
Alternatively:

```bash
bash run.sh --build-package --output-dir /tmp/manager-package
```

Only if you later want system installation, install that deb with apt.
The included system-extension-manager.desktop is for the optional installed manager.

## One-time Update All (0.2.7)

Select **Update All** in the manager window or, from a desktop terminal, run:

```bash
bash run.sh --update-all
```

The manager checks real dpkg status and compares installed versions with bundled
releases. It previews *only* extensions that are already installed **and older** than
the verified release. Disabled/uninstalled extensions stay disabled, current or newer
versions are never downgraded, and partially installed extensions block the batch.
The update plan and each package are checked before modifications, and every package
update uses the existing simulation, root-owned hash-verified stage, and post-install
dpkg readback. A failed upgrade stops the batch; earlier completed upgrades are not
rolled back. Individual packages may still request administrator authorization.

After installed extensions are handled, Update All launches the portable **Security
Updates** terminal, where APT security candidates are separately reviewed and require
typing `UPDATE` to authorize package installation. The terminal stays open and writes
its own full transcript. This is a single manually triggered workflow, **not an
unattended upgrade**. No scheduler, missing extension installation, kernel/NVIDIA/DKMS/
firmware/boot upgrade, or manager self-update is performed. Update All uses the releases
bundled in this manager version; it does not automatically download new releases from
GitHub.

## Extensions

- **ZIP and Trash**: Nemo context-menu verified ZIP creation, keeping originals by default. Optional CLI --trash-originals warns about concurrent writers.
  Symbolic links are stored as links without following targets, including dangling and directory links.
- **HomeBackUp**: Independent Borg recovery backup extension. Installs into the manager as a normal system package with status/readback and optional source build. After Enable, configure once from the Linux Mint applications menu using `homebackup-ext setup` or `homebackup-ext use-existing` (existing root-only Borg credentials). Reuses `/media/andrew/HomeBackUp/Mint-Recovery-Borg` without deleting existing backups on installation; monthly timer with at most three backup dates. Requires an existing Borg 1.x repo and the configured HomeBackUp disk; `/dev/sdc7` is not included. The extension opens a dedicated GTK window from the manager's Open action or Mint application menu.
- **Link Provider**: Select **Enable / Install** and then **Open** to launch the standalone English GTK window. The desktop application menu and the `link-provider` command also open it. Choose **Enable Desktop Links** for `caldav-run://` integration, or **Update Desktop Links** to switch an existing portable registration to the installed application. Existing link records are kept. Local commands run as the desktop user with privilege elevation blocked within the launched process tree.
- **Security Updates**: **No installation required.** Select the row and click **Run in Terminal**.
  A terminal launches the bundled Python script, refreshes indexes with sudo, lists the eligible Ubuntu
  noble-security upgrades, simulates the exact transaction and requires typing UPDATE to install.
  Kernel/NVIDIA/DKMS/firmware/boot packages are protected. The terminal stays open until Enter after completion or failure. Its stdout, stderr and real exit code are saved under the private `~/.local/state/system-extension-manager/logs/security-updates-terminal-*.log` file, whose exact path is shown in the manager's launch log. No service or timer is installed.
- **Anki Time Travel**: CLI and desktop import of historical Anki PDFs into local WordPress.
  Relative paths, numeric download suffixes, GMT evaluation and exact-post permalink verification are included.
  Requires an existing accessible WordPress installation and WP-CLI. Installing or opening the application does not start an import.

Select Anki Time Travel, click **Enable / Install**, then **Open**.
An existing installed version is detected automatically. Use Update to upgrade it to the bundled version.
Disable removes the extension package without deleting WordPress posts, PDFs, settings or logs.
ZIP and Trash is used from Nemo's context menu and has no standalone application window.

## Log history

Open **Log History...** in the manager to view saved operation logs and Security Updates
terminal transcripts, including logs from earlier versions. The list shows the most
recently written files first. Select a log to preview it, use **Refresh logs** to read new
terminal output, or use **Open log folder** to find the originals in your file manager.
**Save log...** exports the full selected file, including output outside the preview.

The history includes ZIP and Trash and Anki import logs written to the shared directory.
It uses the current user's `$XDG_STATE_HOME/system-extension-manager/logs`
(default `~/.local/state/system-extension-manager/logs`). System journal entries
and output from scripts run outside the manager are stored by those tools separately.

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
bash run.sh --enable link-provider
bash run.sh --open link-provider
bash run.sh --open security-updates  # runs one terminal command, without installing a .deb
```

Full commands, live combined stdout/stderr, stages, exit codes and package-state readback appear in the log.
Logs remain visible and can be copied or saved. Automatic private logs use
`$XDG_STATE_HOME/system-extension-manager/logs`, default `~/.local/state/system-extension-manager/logs`.
Opening an extension keeps its execution log active until its window is closed.

Build from source verifies SHA-256-pinned bundled files and builds as the regular user in a fresh cache directory.
The generated deb is checked for package identity, version and architecture before apt dependency simulation and authorized installation.
Root builds are refused. Missing build tools are reported. This version does not download arbitrary source repositories
or automatically port incompatible source code.

Run the manager as your desktop user. Package changes and explicitly requested security updates require administrator authorization.
Installing/removing an extension affects all users. Removing the manager itself leaves independently installed extensions intact.

## Build extension packages and test

From this source folder:

```bash
python3 build.py --extensions-only
python3 -m unittest discover -s tests -v
```

GUI tests require a graphical session (or xvfb-run). Running build.py without arguments
prints help and builds nothing. Tests do not build the main manager deb.
Source builds require dpkg-deb and xz; ZIP and Trash requires Nemo, zip, unzip and GIO. HomeBackUp requires BorgBackup 1.x, GTK 3 and a separately enrolled encryption passphrase. Launching `homebackup-ext` as the ordinary desktop user now opens a GTK window. Status requires no administrator privileges; privileged buttons invoke a standard PolicyKit prompt. The scheduler may genuinely be disabled and the UI reports this state rather than silently re-enabling it. Package installation does not request a Borg password; use the extension setup command afterwards.
Anki Time Travel requires the existing WP-CLI and WordPress environment. The 0.1.6 import refuses unrelated matching-title/date posts, hashes WordPress media against the source PDF before publishing, and stores a read-back-verified source marker. Existing verified import posts may still be updated; published attachments can be publicly accessible.

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

The GitHub Actions `System Extension Manager` workflow builds a portable source ZIP **with four extension debs plus the portable security script** and an optional System Extension Manager `.deb` for download as CI artifacts. In the manager select **HomeBackUp** and choose **Enable / Install**; the system package manager requests one administrator authorization for installation. Updating an already-installed extension uses **Update**, and removing a missing package is a no-op. The Borg encryption password is a separate credential needed only for first setup or repository access. No sensitive backup data or credentials are shipped. Reinstall-and-restore and live Mint GUI installation are not yet acceptance-tested.

Raw Git checkouts include four matching extension packages, valid source pins and the portable updater. Run `bash system-extension-manager/run.sh` directly; no build or manager installation is needed. CI validates the committed tree before rebuilding.

### HomeBackUp GUI update

The HomeBackUp v0.1.6 application uses the native GTK 3 interface by default, with archive listing, retention preview, structural and data verification, monthly timer status, enable/disable, and one-time Borg password enrollment. Administrative actions use PolicyKit; ordinary status requires no sudo. Package installation does not enable the timer, and upgrading does not change the current timer state.

### Manual Security Updates (Linux Mint 22.x)

**The script requires no installation.** Select **Security Updates** and click **Run in Terminal**.
The manager launches a command equivalent to:

```bash
/usr/bin/python3 sources/security-updates/security_updates.py --interactive
```

The terminal refreshes package indexes with `sudo`, lists eligible Ubuntu security updates,
previews an exact APT simulation and only installs after typing `UPDATE`. Cancelling leaves
packages unchanged. If `sudo` or a compatible graphical terminal is unavailable, it stops
without installing extra programs.

`bash run.sh --open security-updates` starts the same command. `--enable`, `--disable`,
`--update` and `--build` are deliberately rejected for this portable tool.

The script ships inside the portable source ZIP and optional manager package, **not as its own .deb**.
It creates no automatic updates, timers, package holds, package removals or reboots. APT may
restart system services and interrupted installations cannot be rolled back automatically.
Previously installed legacy `mint-security-updates-extension` packages are not used or
uninstalled automatically.

Portable updates require a trusted source copy and a terminal kept open through completion. The manager checks the source checksum before launching. Closing a terminal may interrupt APT; no automatic rollback exists.

### Additional warnings (not fixes)

Selected tools describe the root-owned APT install staging, isolated updater source staging and guarded backup locks, while identifying residual plan/backup consistency risks. The package confirmation and CLI logs retain these notices. HomeBackUp 0.1.6 includes the lock notice in its GTK window and runtime scripts. Legacy PDF extraction and website-menu tools warn about output links and unrestricted icon resources. See SECURITY_STATUS.md. Publication remains intentional.
