# User tools and system extensions

User tools register existing local scripts without copying or removing them.
They are stored under `$XDG_CONFIG_HOME/mint-toolbox/extensions` (default `~/.config/mint-toolbox/extensions`).
System extensions are reviewed Debian packages managed separately; see SYSTEM_PLUGINS.md.

```bash
mint-toolbox --extension-add /absolute/path/tool.py --name "My tool" --category "Development"
mint-toolbox --extensions
mint-toolbox --disable user-tool-ID
mint-toolbox --enable user-tool-ID
mint-toolbox --extension-remove user-tool-ID
```

Use the actual generated user-tool ID printed by registration. Unregistering preserves the executable and manual.
The GUI also supports **Add user tool...**, **Disable tool**, **Enable tool**, and **Unregister**.

A data-only manifest uses schema_version 1 and a unique `user-` ID. Required fields are name,
category, description and an absolute executable path. An optional absolute HTML/Markdown manual path is supported.
Actions declare key, label, fields, argv and severity. Field kinds are text, file, folder, file_or_folder and boolean.
Argument literals never perform interpolation. Dynamic values use objects such as `{"field":"source"}`
or `{"field":"source","flag":"--input"}`. Discovery validates data without executing the tool.

Disabling is independent of marking an entry as removed. Restoring an entry does not silently enable it.
User-defined names, descriptions and filenames are preserved in their original language.
