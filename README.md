# LauncherOnOS

An interactive, user-scoped command-line manager for personal Linux scripts and utility launchers. Designed for Linux Mint / Ubuntu / Debian. Python 3.10+ and the standard library only.

## Quick start

```bash
bash install.sh
# On later versions: bash install.sh --upgrade
~/.local/bin/launcheronos menu
```

Or run directly: `python3 launcheronos.py menu`.

## Commands

| Command | Purpose |
| --- | --- |
| `launcheronos scan ~/bin` | Discover local tools without running them |
| `launcheronos search wechat` | Search descriptions and names |
| `launcheronos install ~/bin/my-tool.sh` | Copy a standalone script into manager-owned storage |
| `launcheronos register ~/bin/podman-compose` | Track an existing binary/venv launcher, **without copying** it |
| `launcheronos list` | List registered tools |
| `launcheronos info my-tool` | Show a registered entry |
| `launcheronos run my-tool` | Launch explicitly selected tool |
| `launcheronos export all ~/tools-backup.tar.gz` | Export managed scripts and metadata |
| `launcheronos uninstall my-tool` | Remove a managed copy, or unregister an external entry |

Running `launcheronos` without arguments opens the interactive menu.

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

**Privacy**: This repository does not contain personal shell scripts, WordPress credentials, Thunderbird profiles, or any uploaded `bin.zip` content.

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
