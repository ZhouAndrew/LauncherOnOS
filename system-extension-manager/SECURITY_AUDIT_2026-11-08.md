# System Extension Manager security and bug review — 2026-11-08

Scope: the active `system-extension-manager/` application (version 0.2.4), its
four packaged extensions (ZIP and Trash, Anki Time Travel, HomeBackUp and Link
Provider), its portable Security Updates tool, build scripts, unit tests and
GitHub Actions. The deprecated `mint-toolbox/` implementation is **not** the
active manager. This is source inspection and CI regression work, **not** a
penetration test or live acceptance of the user's workstation. It cannot prove
the absence of all bugs or malicious code. Severity reflects potential impact
with the specified preconditions, not proof of exploitation.

## Confirmed findings

| ID | Severity | Area | Finding and relevant behavior | Status |
| --- | --- | --- | --- | --- |
| MGR-01 | High (distribution confidentiality) | `build.py:build_manager`, CI portable ZIP | Building the optional manager .deb with `copytree(ROOT, ...)` copied **arbitrary files** present in the source tree beyond the catalog's verified resources, including untracked local data. Hash checks on bundled debs did not constrain what else was packaged. The ZIP workflow also zipped the working directory rather than a tracked-file set. | **Fixed in this change:** explicit payload whitelist; every pinned extension source verified before manager .deb packaging; portable source ZIP generated using `git archive`. Regression tests added. |
| MGR-02 | High (conditional local privilege escalation / root-file integrity) | `lifecycle.py:command/change` | Extension .deb is hashed, but APT later reads the user-controlled path after a separate privilege authorization. On writable checkout/cache paths, a concurrent actor with write access could replace it between validation and privileged use. This is a TOCTOU risk, not an observed exploit. | **Unfixed**; preexisting warning retained. Stronger design requires privilege-bound verification/copy into a root-owned private staging area immediately before APT, plus readback. |
| MGR-03 | High (conditional root-file integrity) | `sources/homebackup/backup.sh`, generated `run-backup` from `setup.sh` | Root uses `exec 8>...lock` and `exec 9>...lock`, which follow preplanted symlinks and truncate their targets. Exploitability depends on an attacker being able to control the lock path or its parent directory. | **Unfixed**; user-visible warnings retained. Replace redirection with safe no-follow open and owner/type checks in both generated and direct paths; rebuild/version the extension only after tests. |
| MGR-04 | High (conditional privilege boundary) | `sources/security-updates/security_updates.py` | The script elevates itself using `sudo /usr/bin/python3 <user-writable script>`. Python's default import search can load extra same-directory modules, and the script can itself be replaced after the initial checksum check. This does **not** mean such a module was found. | **Unfixed**; existing warning retained. Requires a trusted/root-owned execution copy and import isolation; `-I` alone does not close the executable replacement window. |
| MGR-05 | Medium (misleading success / diagnostics) | `sources/link-provider/link-provider:use_link` | An application link prints `Started: ID` immediately after `Popen`, with stdout/stderr discarded; the application can exit immediately or require a separate backend without any useful error. The message confirms process creation, not readiness. | **Unfixed**. Define a process/readiness contract before changing accepted Link Provider package behavior; do not silently autostart an unknown backend. |
| MGR-06 | Medium (intentional destructive behavior) | `sources/anki-time-travel/anki-time-travel.sh` | Matching historical posts are reused and published, content/taxonomies can be overwritten, and same-path media may refer to earlier bytes. Uploaded PDFs can be publicly reachable. | **Accepted behavior, not remediated**. Existing publication warnings must remain in CLI and GUI. Back up WordPress and verify outputs. |
| MGR-07 | Medium (intentional non-atomic behavior) | `sources/zip-trash/zip_trash.py` | `--trash-originals` verifies then moves inputs one by one. Concurrent writers can change sources after verification; failure partway through Trash can leave partial moves. The default **keeps originals**. | **Accepted opt-in limitation**, existing warning retained. Never imply atomic snapshot or rollback. |
| MGR-08 | Low (documentation drift) | `SECURITY_STATUS.md` | Security status still described active manager v0.2.3 and omitted the Link Provider extension, while the active catalog was v0.2.4 with Link Provider. | **Fixed in this change.** |

## Additional observations requiring testing

- `lifecycle.change` uses an APT simulation, a package-version readback and explicit
  driver/kernel removal checks. These are valuable but cannot make the simulation
  and the subsequent privileged APT transaction atomic.
- Installed package status does not establish that an extension's background service
  or the CalDAV-related backend is running. The Link Provider reports command dispatch;
  it does not provide application-specific health checks.
- `HomeBackUp` setup and use-existing intentionally enable the monthly timer and
  warn in the GTK flow. The package installation itself does not enable that timer.
  Real systemd shutdown/upgrade, pruning and restore tests remain necessary.
- The GUI does not offer cancellation for a long-running APT or extension process;
  force-killing package operations would be unsafe. A coordinated cancellation
  design would be needed before treating this as a quick UI-only fix.
- Link Provider's locally registered aliases can launch real programs via a
  user-opted-in URL scheme. Treat links from untrusted web pages as untrusted input;
  do not represent `caldav-run://` as a general authentication boundary.

## Validation and safety constraints

- Automated test added: an untracked fake secret must **not** appear in the
  manager .deb; required bundled assets remain included.
- Automated test added: modifying a SHA-256-pinned extension source must stop
  packaging before output generation.
- Automated test added: traversal paths and symlinked inputs are refused.
- The established package identity, release versions, prebuilt extension .debs
  and pinned catalog hashes are unchanged. This change does **not** upgrade
  installed extensions or modify any real WordPress, APT, backup or CalDAV state.
- CI will build and test on Ubuntu. Passing CI is not equivalent to live
  Linux Mint 22.x acceptance. Sensitive root operations and backup pruning were
  deliberately **not** run in this review.

## Critical remediation follow-up (System Extension Manager 0.2.5)

The table above records the **initial review**; the following is the newer
implementation status in PR #13. Do not mistake this source change for an
upgrade of already installed Linux Mint extensions.

| Finding | Security release status | Remaining limitation |
| --- | --- | --- |
| MGR-02 privileged extension APT path | **Fixed the local-package replacement window**: root opens the approved .deb without following final symlinks, copies the exact opened bytes to a root-owned temporary directory, rechecks SHA-256 and package metadata, reruns APT simulation, and installs from that same staged file. | APT dependency metadata/repositories can still change between separate simulation and actual transaction; live authorization and signed repository trust remain necessary. |
| MGR-03 root HomeBackUp lock-file truncation | **Fixed in HomeBackUp 0.1.6 source and rebuilt .deb**: safe_lock.py uses dirfd, O_NOFOLLOW, no O_TRUNC, uid/type/hardlink and directory-mode verification, then passes a locked fd to bash (runner and direct backup). | Earlier installed HomeBackUp builds must be explicitly updated; backups of actively modified application data may be inconsistent. |
| MGR-04 portable updater root imports / writable-script race | **Fixed**: every sudo operation uses Python -I and an isolated, SHA-256-verified root-owned snapshot of the approved script; root actions reject unisolated/non-root-owned entry. | Linux Mint APT can still restart services; manual review and failed-install recovery are required. No updater service is installed. |
| MGR-05 Link Provider false success | **Fixed misleading success** in Link Provider 0.2.2: immediate nonzero exit reports failure; long-running or fast-zero exits explicitly say readiness not verified. | Application-specific backend liveness still cannot be inferred generically; no automatic backend startup without an explicitly defined backend. |
| MGR-06 Anki WordPress collision/stale bytes | **Partial data-integrity fix**, Anki Time Travel 0.1.6: refuse unrelated same-title/date posts; verify local PDF SHA-256 against actual WordPress attachment bytes before publication; write/read back source marker. | Intentionally published prior Anki posts can still be updated; WordPress media URLs may be public. No change to required publish behavior. |
| MGR-07 opt-in ZIP Trash non-atomicity | **Mitigated** in ZIP 0.4.5: reread remaining source snapshots before each Trash move, read back source disappearance, and report partial completion. Default still retains originals. | Moving multiple files to system Trash cannot be an atomic multi-file transaction. A concurrent writer can still race after a validation. |

Rebuilt packages and checksum catalog are tracked in the PR; the temporary
privileged CI rebuild workflow was removed after use. All new packages are
versioned separately from the older binaries. Test coverage includes real
package building/metadata checks, source hash pinning, a simulated adversarial
package replacement, backup lock symlinks/hardlinks, updater replacement,
Link Provider failure, PDF collision/stale attachment, and ZIP concurrent
writes. This is **not** a claim of live Mint backup or real APT acceptance.

## Suggested next hardening sequence

1. Fix the HomeBackUp root lock paths with no-follow, ownership and file-type
   checks, update generated runner and package, and test under adversarial
   symlinks before shipping a new .deb.
2. Eliminate privileged APT and updater script TOCTOU with root-owned staging
   and narrowly authorized execution; preserve manual review and NVIDIA/kernel
   exclusions.
3. Add precise Link Provider start-failure diagnostics, backend status display
   where an explicitly configured backend exists, and test Thunderbird link
   dispatch without claiming process creation proves application readiness.
4. Re-run full source/package hash checks, GUI tests and real Linux Mint
   interactive acceptance before calling any of the residual findings fixed.
