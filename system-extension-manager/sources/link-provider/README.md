# Link Provider 0.3.0

Link Provider is a Linux desktop tool for websites, app links and fixed local commands.

## Open the manager

In System Extension Manager, select **Link Provider → Enable / Install → Open**.
After installation, you can also select **Link Provider** from the applications menu
or run `link-provider` from a terminal. All three open the same GTK window.

1. Click **Add Link**, choose **Local command**, and give the link an ID such as `open-home`.
2. Enter an executable name or use **Browse…** to pick a file. For example, enter `xdg-open` and put your home directory's full path in **Arguments**. Quote arguments containing spaces.
3. Use **Test Launch** to open the target and **Copy Link** to copy `caldav-run://open-home`. Use **Edit**, **Disable**, or **Delete** to manage it.
4. Click **Enable Desktop Links** to let other apps open the short links. This uses your current user's desktop settings. If the portable version already handles your links, click **Update Desktop Links** to switch to the installed application.

Choose **Website or app link** to save a URL instead of an executable. Link IDs use lowercase ASCII letters, digits and hyphens.

## Command links and permissions

The link carries only the ID. Link Provider looks up the executable and fixed arguments in your local registry and passes them directly to the program. It rejects direct use of `sudo` and other common privilege elevation tools. Local commands launch as the current desktop user with Linux's `no_new_privs` flag, which prevents their process and its descendants from gaining privileges through set-user-ID executables or file capabilities.

Register only commands you trust. Other applications can trigger enabled links after desktop registration. The launch restriction applies to the command's process tree. Services contacted separately through the desktop session or system bus enforce their own permissions.

**Test Launch** confirms dispatch, not application or backend readiness. A rapid nonzero exit is reported as an error. A command that exits with code zero or remains running may still rely on an unavailable backend; inspect its logs and verify the target opened.

## Terminal and application integration

```bash
link-provider --help
link-provider add-app open-home xdg-open "$HOME"
link-provider link open-home
link-provider test open-home
gio open caldav-run://open-home
```

| Operation | Command |
|---|---|
| List registrations | `link-provider list` or `link-provider list --json` |
| Add a URL | `link-provider add web https://example.org/` |
| Edit a URL or command | `link-provider edit ID URL` or `link-provider edit-app ID PROGRAM [ARG ...]` |
| Enable or disable | `link-provider enable ID` or `link-provider disable ID` |
| Delete a link | `link-provider remove ID` |
| Check without launching | `link-provider check ID` |
| Open a link | `link-provider open ID` or `link-provider open caldav-run://ID` |
| Show or copy a short link | `link-provider link ID` or `link-provider copy ID` |
| Format an existing link for a CalDAV description | `link-provider link ID --marker` |
| Manage desktop integration | `link-provider register-handler`, `handler-status` or `unregister-handler` |

The configuration is shared with 0.1.0 and defaults to `~/.config/link-provider/links.json`, respecting `XDG_CONFIG_HOME`. Terminal clipboard operations use `wl-copy`, `xclip` or `xsel`. The graphical **Copy Link** button uses the desktop clipboard through GTK.

Removing the package removes its command and application menu entry. Your user configuration is kept. A desktop link registered to the package stops resolving while the package is absent.

## Custom desktop schemes

Select **Desktop Scheme…**, enter a scheme such as `study`, and save.
The manager registers it with the desktop and copies links such as `study://anki`.
Each link selects an existing saved ID and its fixed arguments.

The equivalent CLI setup is:

```bash
link-provider add-scheme study
link-provider register-handler
link-provider link anki --scheme study
```

## Run a preset from another device

1. Save a **Local command** preset and select **Allow LAN** for that preset.
2. Open **LAN Settings…** and enter the Mint machine's reachable hostname or IPv4 address.
   Choose the HTTPS and optional HTTP redirect ports. Choose a certificate/key with
   the native file chooser, or leave both paths empty to generate a certificate.
3. Trust that certificate on the other device and set a dedicated password with
   **Set LAN Password…**.
4. Select **Start LAN**, then **Copy LAN Link**. Open the copied HTTPS link on the
   other device, enter the password there and select **Run**.
5. Select **Stop LAN** to end access. Closing the Link Provider window also ends
   its LAN listener.

The HTTP address uses the configured HTTP port and redirects to the HTTPS password
page. Only the HTTPS endpoint accepts a password and a run request.
The listener requires the expected Host and Origin. Wrong passwords are throttled.
Remote requests select an individually authorized preset and cannot supply a command
or extra arguments. Commands run as the desktop user with `no_new_privs`.
Changing a command revokes its LAN permission until explicitly allowed again.

For terminal use, `configure-lan --host HOST`, `set-lan-password`,
`allow-lan ID` and `start-lan` provide the same configuration and listener.
The terminal listener remains active until interrupted.
