"""GTK interface for the portable Link Provider."""

import json
import os
import shlex
import sys

import gi

os.environ["LANGUAGE"] = "en"
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango


def label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0)
    if style:
        widget.get_style_context().add_class(style)
    return widget


class LinkEditor(Gtk.Dialog):
    def __init__(self, parent, link_id, entry):
        editing = entry is not None
        super().__init__(title="Edit Link" if editing else "Add Link",
                         transient_for=parent, modal=True, use_header_bar=True)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        save = self.add_button("Save" if editing else "Add Link", Gtk.ResponseType.OK)
        save.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(535, -1)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=18)
        self.get_content_area().add(form)
        self.link_id = Gtk.Entry(text=link_id, editable=not editing)
        self.link_id.set_placeholder_text("e.g. open-notes")
        form.pack_start(label("Link ID"), False, False, 0)
        form.pack_start(self.link_id, False, False, 0)
        form.pack_start(label("Lowercase letters, digits and hyphens.", "dim-label"), False, False, 0)

        self.kind = Gtk.ComboBoxText()
        self.kind.append("uri", "Website or app link")
        self.kind.append("app", "Local command")
        form.pack_start(label("Target type"), False, False, 0)
        form.pack_start(self.kind, False, False, 0)
        self.targets = Gtk.Stack(vhomogeneous=False)
        form.pack_start(self.targets, False, False, 0)

        self.uri = Gtk.Entry(activates_default=True)
        self.uri.set_placeholder_text("https://example.org/")
        uri_form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        uri_form.pack_start(label("Destination URL"), False, False, 0)
        uri_form.pack_start(self.uri, False, False, 0)
        self.targets.add_named(uri_form, "uri")

        app_form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.program = Gtk.Entry(activates_default=True)
        self.program.set_placeholder_text("e.g. xdg-open or /usr/bin/gedit")
        program_row = Gtk.Box(spacing=6)
        program_row.pack_start(self.program, True, True, 0)
        browse = Gtk.Button(label="Browse…")
        browse.connect("clicked", self.browse)
        program_row.pack_start(browse, False, False, 0)
        app_form.pack_start(label("Executable"), False, False, 0)
        app_form.pack_start(program_row, False, False, 0)
        app_form.pack_start(label("Arguments (optional)"), False, False, 0)
        self.arguments = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True)
        scroll = Gtk.ScrolledWindow(min_content_height=56, shadow_type=Gtk.ShadowType.IN)
        scroll.add(self.arguments)
        app_form.pack_start(scroll, False, True, 0)
        hint = label('Quote an argument containing spaces, e.g. "/home/me/My Notes".', "dim-label")
        hint.set_line_wrap(True)
        app_form.pack_start(hint, False, False, 0)
        hint = label("Only register commands you trust. This link can be opened by other apps.", "dim-label")
        hint.set_line_wrap(True)
        app_form.pack_start(hint, False, False, 0)
        self.targets.add_named(app_form, "app")

        self.error = label("", "error")
        self.error.set_line_wrap(True)
        self.error.set_selectable(True)
        form.pack_start(self.error, False, False, 0)
        self.kind.connect("changed", lambda combo: self.targets.set_visible_child_name(combo.get_active_id()))
        if editing and entry["kind"] == "app":
            self.program.set_text(entry["target"][0])
            self.arguments.get_buffer().set_text(shlex.join(entry["target"][1:]))
        elif editing:
            self.uri.set_text(entry["target"])
        self.show_all()
        self.kind.set_active_id(entry["kind"] if editing else "app")
        (self.kind if editing else self.link_id).grab_focus()

    def browse(self, _button):
        chooser = Gtk.FileChooserNative.new("Choose an executable", self, Gtk.FileChooserAction.OPEN,
                                            "Choose", "Cancel")
        chooser.set_current_folder("/usr/bin")
        if chooser.run() == Gtk.ResponseType.ACCEPT:
            self.program.set_text(chooser.get_filename())
        chooser.destroy()

    def command(self):
        name = self.link_id.get_text().strip()
        operation = "edit" if not self.link_id.get_editable() else "add"
        if self.kind.get_active_id() == "uri":
            return name, [operation, name, self.uri.get_text().strip()]
        buffer = self.arguments.get_buffer()
        arguments = shlex.split(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True))
        return name, [f"{operation}-app", name, self.program.get_text(), *arguments]


class LinkManager(Gtk.Window):
    def __init__(self, script, read_links, link_error, desktop_id, lan_settings, configured_schemes):
        super().__init__(title="Link Provider", default_width=850, default_height=490)
        self.script = str(script)
        self.read_links = read_links
        self.link_error = link_error
        self.desktop_id = desktop_id
        self.lan_settings = lan_settings
        self.configured_schemes = configured_schemes
        self.server = None
        self.connect("delete-event", self.close_server)
        self.links = {}
        self.busy = False
        self.handler = None
        self.handler_current = False

        header = Gtk.HeaderBar(title="Link Provider", subtitle="Manage links and local commands",
                               show_close_button=True)
        self.set_titlebar(header)
        self.add_button = Gtk.Button(label="Add Link")
        self.add_button.get_style_context().add_class("suggested-action")
        self.add_button.connect("clicked", lambda _button: self.edit())
        header.pack_start(self.add_button)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, border_width=16)
        self.add(content)
        desktop_row = Gtk.Box(spacing=10)
        self.desktop_status = label("Checking desktop integration…", "dim-label")
        self.desktop_status.set_ellipsize(Pango.EllipsizeMode.END)
        desktop_row.pack_start(self.desktop_status, True, True, 0)
        self.desktop_button = Gtk.Button(label="Enable Desktop Links")
        self.desktop_button.set_sensitive(False)
        self.desktop_button.connect("clicked", self.toggle_handler)
        desktop_row.pack_end(self.desktop_button, False, False, 0)
        content.pack_start(desktop_row, False, False, 0)
        setup = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                            min_children_per_line=1, column_spacing=8, row_spacing=6)
        for title, callback in (("Desktop Scheme…", self.scheme_dialog),
                                ("LAN Settings…", self.lan_dialog),
                                ("Set LAN Password…", self.password_dialog)):
            button = Gtk.Button(label=title)
            button.connect("clicked", callback)
            setup.add(button)
        self.server_button = Gtk.Button(label="Start LAN")
        self.server_button.connect("clicked", self.toggle_server)
        setup.add(self.server_button)
        content.pack_start(setup, False, False, 0)


        self.rows = Gtk.ListStore(str, str, str, str)
        self.table = Gtk.TreeView(model=self.rows, search_column=0)
        for index, title in enumerate(("Link ID", "Type", "Status", "Target")):
            renderer = Gtk.CellRendererText(
                ellipsize=Pango.EllipsizeMode.END if index == 3 else Pango.EllipsizeMode.NONE,
            )
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_resizable(True)
            column.set_expand(index == 3)
            self.table.append_column(column)
        self.table.get_selection().connect("changed", self.update_selection)
        self.table.connect("row-activated", lambda *_args: self.edit_selected())
        table_scroll = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN)
        table_scroll.add(self.table)
        content.pack_start(table_scroll, True, True, 0)
        self.empty = label("No saved links. Select Add Link to get started.", "dim-label")
        self.empty.set_no_show_all(True)
        content.pack_start(self.empty, False, False, 0)

        selected_row = Gtk.Box(spacing=8)
        selected_row.pack_start(label("Link"), False, False, 0)
        self.alias = Gtk.Entry(editable=False, placeholder_text="Select a link")
        selected_row.pack_start(self.alias, True, True, 0)
        self.copy_button = Gtk.Button(label="Copy Link")
        self.copy_button.connect("clicked", self.copy)
        self.copy_lan_button = Gtk.Button(label="Copy LAN Link")
        self.copy_lan_button.connect("clicked", self.copy_lan)
        selected_row.pack_start(self.copy_lan_button, False, False, 0)
        selected_row.pack_start(self.copy_button, False, False, 0)
        content.pack_start(selected_row, False, False, 0)

        action_row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                 min_children_per_line=1, max_children_per_line=5,
                                 column_spacing=8, row_spacing=6)
        self.edit_button = Gtk.Button(label="Edit")
        self.edit_button.connect("clicked", lambda _button: self.edit_selected())
        self.toggle_button = Gtk.Button(label="Disable")
        self.toggle_button.connect("clicked", self.toggle_link)
        self.delete_button = Gtk.Button(label="Delete")
        self.delete_button.connect("clicked", self.delete)
        self.test_button = Gtk.Button(label="Test Launch")
        self.test_button.connect("clicked", lambda _button: self.run_selected("test"))
        for button in (self.edit_button, self.toggle_button, self.delete_button):
            action_row.add(button)
        self.lan_button = Gtk.Button(label="Allow LAN")
        self.lan_button.connect("clicked", self.toggle_lan)
        action_row.add(self.lan_button)
        action_row.add(self.test_button)
        content.pack_start(action_row, False, False, 0)

        self.status = label("", "dim-label")
        self.status.set_selectable(True)
        self.status.set_line_wrap(True)
        content.pack_start(self.status, False, False, 0)
        self.refresh()
        self.run_command(["handler-status", "--details"], self.show_handler_status)

    def form_dialog(self, title, fields):
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True, use_header_bar=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(16)
        box.set_spacing(8)
        entries = {}
        for key, title, value in fields:
            box.pack_start(label(title), False, False, 0)
            entry = Gtk.Entry(text=str(value))
            entry.set_visibility(key not in {"password", "repeat"})
            if key in {"cert", "key"}:
                row = Gtk.Box(spacing=6)
                row.pack_start(entry, True, True, 0)
                browse = Gtk.Button(label="Browse…")
                def choose(_button, target=entry):
                    chooser = Gtk.FileChooserNative.new("Choose a file", dialog,
                                                        Gtk.FileChooserAction.OPEN, "Choose", "Cancel")
                    if chooser.run() == Gtk.ResponseType.ACCEPT:
                        target.set_text(chooser.get_filename())
                    chooser.destroy()
                browse.connect("clicked", choose)
                row.pack_start(browse, False, False, 0)
                box.pack_start(row, False, False, 0)
            else:
                box.pack_start(entry, False, False, 0)
            entries[key] = entry
        error = label("", "error")
        error.set_line_wrap(True)
        box.pack_start(error, False, False, 0)
        dialog.show_all()
        return dialog, entries, error

    def password_dialog(self, _button):
        dialog, entries, error = self.form_dialog("Set LAN Password", [
            ("password", "New password (at least 12 characters)", ""),
            ("repeat", "Repeat password", "")])

        def response(widget, choice):
            if choice != Gtk.ResponseType.OK:
                widget.destroy()
                return
            values = {key: entry.get_text() for key, entry in entries.items()}
            widget.set_sensitive(False)

            def done(ok, message):
                if ok:
                    widget.destroy()
                    self.status.set_text(message)
                else:
                    widget.set_sensitive(True)
                    error.set_text(message)
            self.run_command(["set-lan-password", "--stdin"], done, json.dumps(values))
        dialog.connect("response", response)

    def scheme_dialog(self, _button):
        dialog, entries, error = self.form_dialog("Desktop Scheme", [
            ("scheme", "Custom scheme (for example study)", self.configured_schemes()[-1])])

        def response(widget, choice):
            if choice != Gtk.ResponseType.OK:
                widget.destroy()
                return
            def saved(ok, message):
                if ok:
                    widget.destroy()
                    self.refresh(self.selected())
                    self.run_command(["register-handler"], registered)
                else:
                    error.set_text(message)
            def registered(ok, message):
                self.status.set_text(message)
                self.run_command(["handler-status", "--details"], self.show_handler_status)
            self.run_command(["add-scheme", entries["scheme"].get_text().strip()], saved)
        dialog.connect("response", response)

    def lan_dialog(self, _button):
        if self.server:
            self.status.set_text("Stop LAN before changing its settings.")
            return
        settings = self.lan_settings()
        dialog, entries, error = self.form_dialog("LAN Settings", [
            ("host", "Mint hostname or IPv4 address reached by the other device", settings.get("host", "")),
            ("bind", "Listen address", settings.get("bind", "0.0.0.0")),
            ("port", "HTTPS port", settings.get("port", 8765)),
            ("http_port", "HTTP redirect port (0 disables it)", settings.get("http_port", 8764)),
            ("cert", "Certificate file (leave both paths empty to create a certificate)", settings.get("cert", "")),
            ("key", "Private key file", settings.get("key", ""))])
        note = label("Trust this certificate on the other device before entering your password. "
                     "HTTP links open the HTTPS password page. LAN stops when this window closes.")
        note.set_line_wrap(True)
        note.set_max_width_chars(65)
        dialog.get_content_area().pack_start(note, False, False, 0)
        note.show()
        def response(widget, choice):
            if choice != Gtk.ResponseType.OK:
                widget.destroy()
                return
            arguments = ["configure-lan"]
            for key, entry in entries.items():
                arguments.extend(["--" + key.replace("_", "-"), entry.get_text().strip()])
            widget.set_sensitive(False)
            def saved(ok, message):
                if ok:
                    widget.destroy()
                    self.status.set_text(message)
                    self.update_selection()
                else:
                    widget.set_sensitive(True)
                    error.set_text(message)
            self.run_command(arguments, saved)
        dialog.connect("response", response)

    def copy_lan(self, _button):
        name = self.selected()
        settings = self.lan_settings()
        if name and settings:
            authority = settings["host"]
            if settings["port"] != 443:
                authority += ":" + str(settings["port"])
            value = "https://" + authority + "/run/" + name
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(value, -1)
            clipboard.store()
            self.status.set_text("Copied " + value)

    def toggle_server(self, _button):
        if self.server:
            self.server.send_signal(15)
            self.status.set_text("Stopping LAN…")
            return
        self.server_button.set_sensitive(False)
        try:
            child = Gio.Subprocess.new([sys.executable, self.script, "start-lan"],
                                       Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
        except GLib.Error as exc:
            self.server_button.set_sensitive(True)
            self.status.set_text(str(exc))
            return
        self.server = child
        stream = Gio.DataInputStream.new(child.get_stdout_pipe())

        def ready(source, result):
            try:
                line, _length = source.read_line_finish_utf8(result)
            except GLib.Error as exc:
                line = str(exc)
            if self.server is child and line:
                self.status.set_text(line)
                self.server_button.set_label("Stop LAN")
                self.server_button.set_sensitive(True)

        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, ready)
        child.wait_async(None, lambda process, result: self.server_exited(process, result))
        self.server_button.set_sensitive(True)

    def server_exited(self, process, result):
        process.wait_finish(result)
        if self.server is process:
            self.server = None
            self.server_button.set_label("Start LAN")
            self.server_button.set_sensitive(True)
            error = process.get_stderr_pipe()
            data = error.read_bytes(8192, None).get_data().decode(errors="replace")
            self.status.set_text(data.strip() or "LAN stopped.")

    def close_server(self, *_args):
        if self.server:
            self.server.send_signal(15)
        return False

    def selected(self):
        model, row = self.table.get_selection().get_selected()
        return model[row][0] if row is not None else None

    def update_selection(self, *_args):
        name = self.selected()
        entry = self.links.get(name)
        enabled = entry is not None and entry["enabled"]
        self.alias.set_text(f"{self.configured_schemes()[-1]}://{name}" if name else "")
        self.toggle_button.set_label("Enable" if entry and not enabled else "Disable")
        for button in (self.edit_button, self.toggle_button, self.delete_button):
            button.set_sensitive(entry is not None and not self.busy)
        self.lan_button.set_label("Revoke LAN" if entry and entry.get("allow_lan") else "Allow LAN")
        self.lan_button.set_sensitive(bool(entry and entry["kind"] == "app" and not self.busy))
        self.test_button.set_sensitive(enabled and not self.busy)
        self.copy_button.set_sensitive(enabled)
        self.copy_lan_button.set_sensitive(bool(enabled and entry.get("allow_lan") and self.lan_settings()))
        self.add_button.set_sensitive(not self.busy)

    def refresh(self, name=None):
        try:
            self.links = self.read_links()
        except (self.link_error, OSError, ValueError) as exc:
            self.status.set_text(str(exc))
            return
        self.rows.clear()
        selected = None
        for link_id, entry in sorted(self.links.items()):
            app = entry["kind"] == "app"
            target = shlex.join(entry["target"]) if app else entry["target"]
            row = self.rows.append([link_id, "Command" if app else "URL",
                                    ("Enabled · LAN" if entry.get("allow_lan") else "Enabled") if entry["enabled"] else "Disabled", target])
            if name == link_id:
                selected = row
        self.empty.set_visible(not self.links)
        if selected is None:
            selected = self.rows.get_iter_first()
        if selected is not None:
            self.table.get_selection().select_iter(selected)
        self.update_selection()

    def run_command(self, arguments, callback, input_text=None):
        try:
            process = Gio.Subprocess.new(
                [sys.executable, self.script, *arguments],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE | Gio.SubprocessFlags.STDIN_PIPE,
            )
        except GLib.Error as exc:
            callback(False, str(exc))
            return

        def completed(child, result):
            try:
                _, output, error = child.communicate_utf8_finish(result)
            except GLib.Error as exc:
                callback(False, str(exc))
                return
            success = child.get_successful()
            message = output if success else error or output or "Link Provider did not complete the operation."
            callback(success, message.strip())

        process.communicate_utf8_async(input_text, None, completed)

    def action(self, arguments, refresh=False):
        self.busy = True
        self.update_selection()
        name = self.selected()

        def finished(ok, message):
            self.busy = False
            self.status.set_text(message)
            if ok and refresh:
                self.refresh(name)
            else:
                self.update_selection()

        self.run_command(arguments, finished)

    def edit(self, name=None):
        if self.busy:
            return
        dialog = LinkEditor(self, name or "", self.links.get(name))
        dialog.connect("delete-event", lambda editor, _event: not editor.get_sensitive())

        def response(editor, choice):
            if choice != Gtk.ResponseType.OK:
                editor.destroy()
                return
            try:
                link_id, command = editor.command()
            except ValueError as exc:
                editor.error.set_text(str(exc))
                return
            editor.set_sensitive(False)

            def saved(ok, message):
                if ok:
                    editor.destroy()
                    self.status.set_text(message)
                    self.refresh(link_id)
                else:
                    editor.set_sensitive(True)
                    editor.error.set_text(message)

            self.run_command(command, saved)

        dialog.connect("response", response)

    def edit_selected(self):
        name = self.selected()
        if name:
            self.edit(name)

    def toggle_lan(self, _button):
        name = self.selected()
        entry = self.links.get(name)
        if entry and entry["kind"] == "app":
            action = "deny-lan" if entry.get("allow_lan") else "allow-lan"
            self.action([action, name], refresh=True)

    def toggle_link(self, _button):
        name = self.selected()
        action = "disable" if self.links[name]["enabled"] else "enable"
        self.action([action, name], refresh=True)

    def delete(self, _button):
        name = self.selected()
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.CANCEL, text=f'Delete "{name}"?')
        dialog.format_secondary_text("The saved link will be removed from this computer.")
        dialog.add_button("Delete", Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        if dialog.run() == Gtk.ResponseType.OK:
            self.action(["remove", name], refresh=True)
        dialog.destroy()

    def copy(self, _button):
        value = self.alias.get_text()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(value, -1)
        clipboard.store()
        self.status.set_text(f"Copied {value}")

    def run_selected(self, action):
        self.action([action, self.selected()])

    def show_handler_status(self, ok, message):
        if not ok:
            self.desktop_status.set_text("Desktop integration status unavailable")
            self.desktop_button.set_sensitive(False)
            self.status.set_text(message)
            return
        details = json.loads(message)
        self.handler = details["handler"]
        self.handler_current = details["current"]
        active = self.handler == self.desktop_id
        available = self.handler is None
        if self.handler_current:
            status, button = "Desktop links enabled", "Disable Desktop Links"
        elif active:
            status, button = "Desktop links need to be updated", "Update Desktop Links"
        elif available:
            status, button = "Desktop links disabled", "Enable Desktop Links"
        else:
            status, button = f"Desktop links handled by {self.handler}", "Enable Desktop Links"
        self.desktop_status.set_text(status)
        self.desktop_button.set_label(button)
        self.desktop_button.set_sensitive(active or available)

    def toggle_handler(self, _button):
        self.desktop_button.set_sensitive(False)
        action = "unregister-handler" if self.handler_current else "register-handler"

        def finished(_ok, message):
            self.status.set_text(message)
            self.run_command(["handler-status", "--details"], self.show_handler_status)

        self.run_command([action], finished)


def show_window(script, read_links, link_error, desktop_id, lan_settings, configured_schemes):
    if not Gtk.init_check()[0]:
        raise link_error("No graphical desktop session is available. Use --help for terminal commands.")
    window = LinkManager(script, read_links, link_error, desktop_id, lan_settings, configured_schemes)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
