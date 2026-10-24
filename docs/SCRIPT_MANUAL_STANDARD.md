# Standardized script manuals (v0.1)

LauncherOnOS needs a consistent, source-grounded manual for each personal script. This repository stores the **format**, not users' private script inventories, credentials, venvs or archives.

## Required headings

1. `# <script> — <friendly name>` and category, lifecycle status, risk, install/register/skip.
2. `## Purpose`: one clear paragraph based on the script source.
3. `## Usage`: copyable commands using real supported options.
4. `## Arguments and options`: flags, defaults, positional args, prompts and environment variables.
5. `## Requirements`: platform, tools, external files, absolute paths, permissions.
6. `## Outputs and side effects`: any local/remote creation, modification, deletion, network or privilege use.
7. `## Warnings`: data loss, backups, privacy, and whether dry-run is strictly no-write.
8. `## Source and verification`: source path, SHA-256, and separate static-review, automated-test and real-machine acceptance status.
9. `## LauncherOnOS integration`: recommend install, register or skip, with a reason.

## Launcher integration

- `install`: copy only standalone scripts into manager-owned storage; this never guarantees the script works.
- `register`: track existing paths without copying, especially venv/pipx entrypoints, adjacent-file dependencies and installation-specific launchers.
- `skip`: deprecated tools, historical `.bak` or `.before-*` snapshots and commands not intended for manual launch.

Do not run scripts to generate their documentation. Static review is sufficient for a provisional manual but **is not a runtime acceptance test**. A two-line wrapper does not establish external program behavior.

## Optional private machine-readable catalog

The local user manual may also include `catalog.json` with `schema_version`, `manual_version`, and an `items` array. Each item may include `id`, `name`, `category`, `status`, `risk`, `launcher_action`, `source_path`, `source_sha256`, `manual` and `description`.

Treat this catalog as private user data; do not publish it without review. LauncherOnOS must never infer permission to execute a command merely because it appears in this catalog.
