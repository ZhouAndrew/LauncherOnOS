# Security status — 2026-11-08

## Active product

**ACTIVE / MAINTAINED: System Extension Manager 0.2.4**, under
`system-extension-manager/`. Its independently installed extensions are
ZIP and Trash 0.4.4, Anki Time Travel 0.1.5, HomeBackUp 0.1.5,
Link Provider 0.2.1, plus the built-in terminal-only Security Updates tool.

The 2026-11-08 source audit in
[`system-extension-manager/SECURITY_AUDIT_2026-11-08.md`](system-extension-manager/SECURITY_AUDIT_2026-11-08.md)
records a repaired manager-package untracked-file disclosure path and
outstanding APT/package replacement, Python import, backup-lock, and runtime
readiness limitations. Those outstanding risks are **not claimed fixed**.

**DEPRECATED / NOT ACTIVE: Mint Toolbox**, under `mint-toolbox/`.
Its GUI, CLI and README display this warning. Merging its history does not
reactivate it. The standalone `anki-time-travel/` directory is a compatibility
entry point for that legacy application; use the active manager's extension.
The original LauncherOnOS CLI is a separate script registry, not the active
extension-management GUI.

## Publication is intentional

The user explicitly requires imports to **publish**, not create drafts.
This release preserves their existing output and publication behavior.
Warnings are disclosure, not a claim that import collision/privacy risks are fixed.

| Area | Status and behavior |
| --- | --- |
| Anki imports | **PUBLICATION RETAINED; RESIDUAL RISK.** GUI banner, confirmation dialog, operation log, Bash runtime and code warn that matching title/date may replace existing body/categories/tags, same-path attachments may reuse older bytes, and PDFs can be directly accessible. Back up WordPress and inspect results. |
| WeChat imports/unlocking | **NOT SECURITY-FIXED.** Legacy GUI descriptions/confirmations, catalog, direct CLI and source comments warn about public chats/static files, active HTML/PHP, `rsync --delete` collisions and preprocessing writes even during preview. Publication remains intentional. Do not assume private posts protect uploads. |
| ZIP default / Nemo action | **NON-DESTRUCTIVE DEFAULT.** Create and verify ZIP; KEEP originals. A writer can still change files while archiving. A verified ZIP is not a filesystem snapshot. |
| ZIP `--trash-originals` | **EXPLICIT RESIDUAL RISK.** CLI warning / GUI confirmation and source comments explain that validation and Trash are not atomic. Close writers and inspect before choosing this opt-in. No fallback to permanent deletion. |
| Legacy tar tool | Refuses selected directory symlinks, uses exclusive temporary files and no-clobber publication, and keeps originals. Warns about live changes and manual cleanup. |
| Desktop web launcher | Rejects CR/LF and other control characters at input, final URL and Exec serialization, preventing the reproduced extra-Exec-key injection. |
| HomeBackUp stop | Runs before disk, repository, Borg and password checks. Stops timer and active service; reads back inactive state and service PID, disables and verifies timer. Stop failures propagate. |
| HomeBackUp uninstall | Uses the same verified shutdown helper before removing files; no ignored stop errors. Service uses SIGINT, a bounded stop wait and no forced SIGKILL. Uncooperative processes cause failure rather than unverified removal. |
| HomeBackUp retention | **INTENTIONAL DELETION.** Successful verified backup retains newest archive for each of the latest three backup dates, then deletes other matching mint-* archives and compacts. GUI setup/enable/backup prompts warn that missed schedules may run immediately and pruning is permanent. Preview first. Direct and scheduled backups share an inherited transaction lock through create/check/prune. |
| HomeBackUp upgrade | New package's pre-removal script refuses upgrade during active/transitioning backup. **When upgrading from an older package, its old maintenance scripts still run: stop the scheduler and active service first.** This transition needs live Mint verification. |
| CalDAV legacy task tool | Defaults to HTTPS and refuses HTTP before dependencies/password handling. Plain HTTP requires `--allow-insecure-http` and warns about credential/data exposure. Bulk recurring-task completion still lacks independent readback and warns accordingly. |
| Diagnostic reports | Random exclusive report creation with umask 077 / mode 0600. Warns that logs/configuration snippets are sensitive; review before sharing. |
| APT operations | Simulate both installation and removal, reject unrelated removals and implicit kernel/NVIDIA changes before authorization. No broad system upgrade or security-update timer is installed. |
| Source distribution | Rebuilt extension packages and source pins; removed stale missing test-check.sh reference. CI verifies committed source/package pins BEFORE rebuilding so rebuilding cannot hide an inconsistent checkout. |
| CI supply chain | Actions pinned to GitHub-resolved commits; explicit contents:read permissions. Third-party runtime dependencies and the account's branch protection settings are outside this code change. |

## Newly integrated manual Security Updates tool

Concurrent main-branch changes added Security Updates, then intentionally made
it a terminal-only portable tool. This architecture is preserved: no updater
extension deb is installed. Its root checks retain trusted Ubuntu security-only
selection, kernel/NVIDIA/DKMS/firmware/boot protection, plan fingerprint,
simulation and installed-version readback. Additional hardening rejects planted
lock files, fixes parser locale, bounds network waits and validates configuration
versions. The manager verifies the portable source checksum before launching.
The terminal warns about service restarts, partial failures and keeping it open.
No cron/systemd updater is created; actual APT upgrades were not run here.

## Operational limits

### Additional boundary warnings — 2026-11-07

The following five risks are **WARNED, NOT FIXED** in this release. The notices
do not change publication, privilege, locking, package installation or output
semantics, and do not establish that a user's computer has been compromised.

| Unfixed boundary | Visible warning locations |
| --- | --- |
| Portable updater's unlisted same-directory Python modules may run during sudo | Selected tool warning in the active manager, launch log, terminal CLI and source comments. Use a private trusted source copy. |
| Root backup lock-file redirections follow links and can truncate their targets | Selected HomeBackUp warning, GTK window, existing backup/setup/enable confirmations, operation output, standalone/setup/generated runner/admin stderr and source comments. Keep untrusted writers away from the mount root and lock paths. |
| A deb can be replaced between verification and privileged APT reading it | Active manager selected package warning, existing install/update/source-build confirmation, CLI operation log and code comments. The deprecated extension manager also displays it. Use a private trusted package directory. |
| PDF image output may follow existing links and overwrite other writable files | Legacy tool description and action dialog, CLI startup and code comments. Choose a fresh private output directory. |
| Website icon/manifest references can read file:// images or access internal resources | Legacy tool description and confirmation, CLI startup and fetch-path comments. Only local reading/copying was established; automatic external transmission was not demonstrated. |

Anki and WeChat publication remains intentional and retains its existing warning.
The user requested disclosure for these additional findings, not remediation.


- “Enabled” in the manager describes the Debian extension installation. It does
  not mean HomeBackUp's timer is enabled. Open HomeBackUp to inspect the scheduler.
- Updating repository files does not update already-installed packages on a user's
  machine. Run the new source manager and use its explicit Update action.
- Disabling/removing the manager itself does not remove separately installed
  extension packages or previously configured legacy monthly timers.
- Historical Thunderbird experiment scripts and third-party application runtimes
  are not newly certified. The legacy app remains deprecated and warns accordingly.
- No changes to the user's real WordPress site, backup repository, installed
  services, drivers or kernel were made while implementing these changes.

## Verification

Behavioral regression tests exercise control-character injection rejection,
non-destructive ZIP defaults after a late source write, explicit Trash warnings,
directory-link refusal, disable without disk/password, shutdown/readback failure,
uninstall failure propagation, insecure HTTP refusal and dangerous APT plans.
Existing WordPress stub tests still exercise publication and exact permalinks.
Package checks validate all pinned source recipes as an ordinary user.

Local container GIO may report “Trashing on system internal mounts is not
supported.” Tests skip only this specific filesystem capability failure;
other Trash failures are still failures. Graphical tests require a display.
Neither mock tests nor CI replace live Mint service shutdown, upgrade, backup
and restore acceptance.
