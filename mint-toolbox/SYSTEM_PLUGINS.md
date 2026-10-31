# System extensions

## Multiple tools

The table shows tool name, bundled version, installed package status and source-build availability.
Search and status filters narrow the list without changing enabled states.
Select a tool to use **Enable / Install**, **Disable / Uninstall**, or **Build from source...**.
There is currently one bundled extension. The table and lifecycle are shared by every catalog entry;
there are no placeholder tools presented as working extensions.

## Live commands and logs

Operations display complete shell-quoted commands before starting them, followed by live combined stdout/stderr,
current stage, command exit code and package status readback. Commands run with argument arrays, without a shell.
Output is English where controlled by Mint Toolbox; filenames and external content are preserved.

The log panel is separate from the description. It remains available after success or failure.
Use **Copy log** or **Save log...**. Logs are automatically saved with mode 0600 under
`$XDG_STATE_HOME/mint-toolbox/logs`, defaulting to `~/.local/state/mint-toolbox/logs`.
Log files can include selected paths and package output; inspect them before sharing.
There is no automatic log expiration; users can remove old log files themselves.

## Installation and compatibility

1. Verify the bundled deb SHA-256, package name, version and architecture.
2. Use apt simulation to check dependency resolution without modifying the system.
3. Request administrator authorization through pkexec for the real apt operation.
4. Read the dpkg database back. Incomplete states are reported rather than shown as disabled.

Disable removes the extension package without autoremove. Dependencies remain installed.
Installation and removal are system-wide. Cancelling authorization reports a failure without inventing an enabled state.

## Building from source

Use **Build from source...** or `mint-toolbox --plugin-build zip-trash`.
This is an explicit alternative when a bundled binary is incompatible or missing; it is not a fallback for every apt error.

Only reviewed source files bundled with the application are supported in this version.
The catalog pins every source file by SHA-256 and declares the build command and required tools.
The manager verifies those files, copies them into a fresh private cache directory, and runs the recipe as the current regular user.
Root source builds are refused. Missing build tools are reported; this version does not install build dependencies automatically.
For this extension, the tools are `python3`, `dpkg-deb`, and `xz` (Debian packages: python3, dpkg, xz-utils).

The recipe must produce exactly one deb. Its package name, version and architecture are verified;
apt then checks dependencies and installs it with administrator authorization.
Sources and outputs remain under `$XDG_CACHE_HOME/mint-toolbox/builds` (default `~/.cache/mint-toolbox/builds`) for diagnosis.
A changed source file fails verification. Deliberate source changes require updating the reviewed recipe hashes.
This version does not fetch arbitrary repositories or promise automatic source porting.

## ZIP and Trash extension

Nemo's native context menu provides **Compress to ZIP and delete** for local files and folders.
Select one or multiple entries from the same directory. Confirm the action to open a live execution window.

The operation calls system zip and unzip, compares each archived file with its original SHA-256,
checks for source changes, publishes the ZIP without overwriting existing names, then uses GIO to move originals to Trash.
Single selections use the original name plus .zip. Multiple selections use Archive.zip.
Existing ZIP names receive numbered suffixes.

There is no permanent-deletion fallback. Compression or verification failure preserves originals.
Trash failure preserves the verified ZIP and reports partial completion. Symbolic links and special files are rejected.
ZIP does not preserve every Linux ACL or extended attribute; this is not a replacement for a full system backup.
Files are checked for changes but are not locked against other applications. Pause edits while compressing.

The package declares Python 3.10+, Tk, zip, unzip, GIO and Nemo dependencies.
Open a new Nemo window after installation/removal; sign out and back in if its menu cache does not refresh.
Nemo interface reference: https://github.com/linuxmint/nemo/blob/master/files/usr/share/nemo/actions/sample.nemo_action

## Adding an extension

Add a reviewed catalog entry with a unique ID and Debian package name, version, relative deb path, SHA-256 and description.
Optionally add a source object with kind `bundled`, `requires`, a `files` mapping of relative paths to SHA-256 values,
and an `argv` array. The standalone `{output}` argument is replaced with a fresh output directory.
Recipes run without a shell. Never place install commands in source recipes.
