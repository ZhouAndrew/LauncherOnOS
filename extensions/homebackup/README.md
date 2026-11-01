# Mint HomeBackUp Extension 0.1.2 — GTK GUI

This standalone `.deb` is distributed **through System Extension Manager** in the same repository. It is a separate system package, and does not require MintBox or LauncherOnOS at runtime.

Run **HomeBackUp** from the Mint application menu, or run `homebackup-ext` as the regular desktop user (no `sudo`). The GTK 3 window provides read-only schedule status, archive listing, cleanup preview, integrity checks, full data verification, timer controls and password setup. System-changing actions use PolicyKit authorization, not a root GUI. Setup requires the separate Borg passphrase once and stores it in a root-only file; it is **not** the Linux administrator password.

If the scheduler reports **disabled**, no automatic backup is currently scheduled. Use the GUI's *Enable monthly backup* button only if you want it enabled; package installation and upgrade do **not** silently enable the timer. Existing archive data is never removed at installation.

Build from this folder (the output file is also bundled in the Extension Manager release):

```bash
python3 build.py --output-dir .
```

Requires Python 3, `dpkg-deb`, xz and shell. The installed application additionally needs Borg 1.x, Python `gi` GTK 3, PolicyKit and systemd. Default Borg repo: `/media/andrew/HomeBackUp/Mint-Recovery-Borg`, UUID `6cb1c243-6bdb-4e82-9301-cf6231b87a66`.

The included `setup.sh` is a **source template for retention selection and the background runner**, not an installer. `backup.sh` is the existing recovery-backup source. Backup schedule: monthly day 1 at 03:00 (catch up on boot, if enabled); retention at most three distinct backup dates, with only newest archive from each date. No deletion unless a new backup and its data integrity verification succeed. Other data partitions, including `/dev/sdc7`, are **not included**. A complete reinstall-and-restore exercise has not been performed on the user's Linux Mint host.

The existing encrypted Borg archive, Timeshift snapshots, and root-only saved passphrase are left untouched by the upgrade.
