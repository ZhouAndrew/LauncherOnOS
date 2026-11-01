# Mint HomeBackUp Extension (0.1.0)

Source for the standalone Linux Mint HomeBackUp `.deb` package. This is maintained within `ZhouAndrew/LauncherOnOS` for now, but **does not depend on or alter LauncherOnOS, MintBox, or Mint Toolbox**. It is a separate package, not a Cinnamon in-process extension.

## Build

```bash
python3 build.py
dpkg-deb --root-owner-group --build build-mint-homebackup-extension/mint-homebackup-extension_0.1.0_all mint-homebackup-extension_0.1.0_all.deb
```

Requirements: Python 3, `dpkg-deb`, and Bash. `backup.sh` is the recovery-backup source. `setup.sh` is retained as the source for the existing retention selector and runner; **do not execute `setup.sh` to install this package**. The package is assembled by `build.py`.

## Usage (after installation)

```bash
sudo apt install ./mint-homebackup-extension_0.1.0_all.deb
homebackup-ext use-existing   # reuse an already enrolled Borg credential, if present
# OR
homebackup-ext setup          # request Borg passphrase one time (separate from system authorization)
homebackup-ext menu
```

Package installation itself does not prompt for a Borg password, initialize a repository, enable backups, or delete archives. `setup`/`use-existing` enables the monthly timer, subject to a check for an already-enabled old timer. Normal administrative actions may still require polkit authorization; **single sudo prompt and single Borg prompt cannot be combined into one universal credential**.

Defaults currently target one verified Linux Mint machine: Btrfs target `/media/andrew/HomeBackUp`, Borg 1.x repo `Mint-Recovery-Borg`, source system UUID and Btrfs target UUID are hard-coded as guards. Review the source and adapt before using on other computers. Passwords are not bundled. Backup passphrase storage is root-only under `/var/backups/homebackup-scheduler/passphrase`. Keep an independent offline recovery copy of the key/passphrase.

Schedule: monthly on the 1st at 03:00 (with missed-run catch-up). On successful backup and verification, retain **at most three mint-* archives from distinct backup dates**, selecting each day's newest; the old snapshots are not removed if a new backup fails. Purging only concerns recognized `mint-*` Borg archives and never Timeshift or other files on HomeBackUp. Preview using `homebackup-ext preview`.

The default backup includes `/home`, selected system directories, installation and driver inventories and database exports. Other partitions including `/dev/sdc7` are **not backed up by default**. This is intended for reinstall-then-selective-restore, not a full disk image. No live Linux Mint installation or disaster-recovery test has been recorded for this `.deb`; build and syntax tests are not a substitute.

## Tests

```bash
bash tests/check-package.sh
```

## Existing backup

The existing Borg archive `mint-20261031T065630Z` is kept in place. Do **not** delete it or reinstall the repository while migrating to this extension.
