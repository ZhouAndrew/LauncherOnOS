# Branch integration check — 2026-11-07

Before adding the new warnings, all existing remote branch tips were already
ancestors of `main` at `aa627305bc9fa7d2bf1bd681649a07f6cb34a6d3`.
Each had zero commits absent from main; no historical branch needed to be merged
again or used to overwrite newer files.

| Remote branch | Result |
| --- | --- |
| feat/anki-time-travel-system | Already included |
| feat/interactive-console-manuals | Already included |
| feat/mint-toolbox-system-plugins | Already included |
| feat/mint-toolbox-v0.4 | Already included |
| feat/system-extension-manager-anki | Already included |
| feat/tool-manager-cli-v1 | Already included |
| fix/reliability-audit-v0.1.1 | Already included |
| fix/security-active-manager-20261106 | Already included |
| merge/all-changes-20261106 | Already included |

The new warning work is integrated through its own reviewed change. No branches
are deleted. System Extension Manager remains active, Mint Toolbox remains
deprecated, imports continue to publish, and Security Updates remains a manual
terminal-only tool with no updater package or automatic schedule.
