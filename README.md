> **CURRENT / MAINTAINED:** [System Extension Manager](system-extension-manager/) is the current, independent project.
>
> **DO NOT USE MINT TOOLBOX — RETIRED / UNSAFE.** Never run, install, update,
> build, test, or recommend the legacy Mint Toolbox application. The existing
> `mint-toolbox/` directory is preserved for historical reference only and
> **must not be modified**. Its automatic CI workflow is disabled. Do not
> mistake independent System Extension Manager components for Mint Toolbox.

# LauncherOnOS

An interactive, user-scoped command-line manager for personal Linux scripts and utility launchers. Designed for Linux Mint / Ubuntu / Debian. Python 3.10+ and the standard library only.

## Quick start

```bash
bash install.sh
# On later versions: bash install.sh --upgrade
~/.local/bin/launcheronos --help
```

Or run directly: `python3 launcheronos.py --help`.

Use your existing Linux terminal as the console. No nested menu or custom REPL.

```bash
launcheronos search wechat
launcheronos info my-tool
launcheronos manual /path/to/manual.md
```

The `manual` command delegates formatted Markdown reading to the existing [Glow](https://github.com/charmbracelet/glow) program (`glow -p FILE.md`). Glow must be installed separately. The core LauncherOnOS script still only needs Python 3.10+ and its standard library.

## Commands

| Command | Purpose |
| --- | --- |
| `launcheronos scan ~/bin` | Discover local tools without running them |
| `launcheronos search wechat` | Search descriptions and names |
| `launcheronos install ~/bin/my-tool.sh` | Copy a standalone script into manager-owned storage |
| `launcheronos register ~/bin/podman-compose` | Track an existing binary/venv launcher, **without copying** it |
| `launcheronos list` | List registered tools |
| `launcheronos info my-tool` | Show a registered entry |
| `launcheronos manual /path/to/manual.md` | Render an existing Markdown manual through Glow |
| `launcheronos run my-tool` | Launch explicitly selected tool |
| `launcheronos export all ~/tools-backup.tar.gz` | Export managed scripts and metadata |
| `launcheronos uninstall my-tool` | Remove a managed copy, or unregister an external entry |

Running `launcheronos` without arguments displays command help.

## Safety and behavior

- No root privileges, background service, automatic execution, or network traffic.
- Installation never runs a script; scripts remain **untrusted** until personally reviewed.
- Original `~/bin` files are never deleted or replaced.
- `install` copies only one **standalone script**; scripts with relative files or a Python virtual environment should be tracked with `register` instead.
- `register` only stores a pointer. Uninstalling an external entry never removes its source.
- Uninstall refuses to remove a managed copy if the file has changed after installation.
- Export bundles managed scripts, but **does not bundle external binaries or virtual environments**. Import/restore is not implemented in v0.1.
- A copied script can still contain hard-coded paths or missing dependencies; installation does not prove it will run.
- State is stored in `~/.local/share/launcheronos/`; override with `LAUNCHERONOS_HOME` for testing.

**Privacy**: Bundled utilities include personal paths and disk identifiers. No backup passwords are shipped. Review import warnings before publishing sensitive content.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## Reliability audit (v0.1.1)

Fixed and regression-tested:
- Exact tool ID validation prevents accidental deletion when an ID contains extra punctuation.
- Archives are staged and published atomically. Failed exports leave no misleading destination archive.
- Registered symlinks are supported; copied scripts continue to reject symlink sources.
- Executable scripts honor their own shebang, preserving Python virtualenv entrypoints.
- Managed scripts are verified before execution, and registry files use private permissions.
- Registry writes are serialized with an advisory file lock so concurrent installs/uninstalls do not lose entries.
- The CLI installer supports an explicit `--upgrade`, backs up an existing LauncherOnOS binary, and refuses to replace an unknown executable.
- Auto-generated IDs support non-ASCII filenames.

Known limitations: standalone script installation does not resolve external dependencies; imported restore archives, automatic upgrades, and whole virtual-environment packaging are not implemented. A registered external tool is never bundled into export archives. The repository's CI tests are not a substitute for verification on the user's own Linux Mint system.


## Companion package: Mint HomeBackUp Extension

The standalone [HomeBackUp Extension](extensions/homebackup/) source and Debian package builder are maintained in this repository, replacing the abandoned MintBox/Toolbox integration path for backup management. It is **not** a runtime dependency of LauncherOnOS and does not change its CLI, installation or security model. Build with `bash extensions/homebackup/tests/check-package.sh` (requires Debian/Ubuntu tools); the extension manages an existing encrypted Borg recovery repository, monthly scheduling, and a maximum of three backup dates. It has not yet been live-tested on Linux Mint for installation and disaster recovery.
## Retired historical code

The retired project is not part of System Extension Manager. It must never be
executed, rebuilt, restored or extracted. Its source tree remains untouched;
maintained extensions have their own source under `system-extension-manager/`.
