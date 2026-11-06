#!/usr/bin/python3
"""HomeBackUp's GTK 3 management window. Never run the GUI as root."""
import os
import subprocess
import sys
import threading


def main():
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib, Pango
    except (ImportError, ValueError) as exc:
        print('无法启动 GTK 图形界面：%s；请安装 python3-gi 和 gir1.2-gtk-3.0。' % exc, file=sys.stderr)
        return 1
    if os.geteuid() == 0:
        print('请以普通桌面用户启动 HomeBackUp 图形界面，不要使用 sudo。', file=sys.stderr)
        return 1

    class Window(Gtk.Window):
        def __init__(self):
            super().__init__(title='HomeBackUp 备份管理器')
            self.set_default_size(820, 610)
            self.set_border_width(16)
            self.set_position(Gtk.WindowPosition.CENTER)
            self.connect('destroy', Gtk.main_quit)
            self.busy = False
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.add(root)
            title = Gtk.Label(label='HomeBackUp · Borg 备份与恢复归档')
            title.set_xalign(0)
            title.get_style_context().add_class('title')
            root.pack_start(title, False, False, 0)
            info = Gtk.Label(label='WARNING: Successful backups permanently prune older mint-* archives. Preview retention first.')
            info.set_xalign(0)
            root.pack_start(info, False, False, 0)
            self.status = Gtk.Label(label='正在读取定时器状态…')
            self.status.set_xalign(0)
            self.status.set_line_wrap(True)
            self.status.set_selectable(True)
            root.pack_start(self.status, False, False, 0)
            controls = Gtk.Grid(column_spacing=8, row_spacing=8)
            root.pack_start(controls, False, False, 0)
            self.buttons = []
            specs = [
                ('刷新状态', 'status'), ('查看归档', 'list'), ('清理预览（不删除）', 'preview'),
                ('检查归档结构', 'check'), ('深度数据校验', 'verify-data'),
                ('立即备份', 'backup'), ('启用每月备份', 'enable'), ('停用每月备份', 'disable'),
                ('配置密码并启用计划', 'setup'), ('复用密码并启用计划', 'use-existing'),
            ]
            for i, (label, cmd) in enumerate(specs):
                btn = Gtk.Button(label=label)
                btn.connect('clicked', self.action, cmd)
                controls.attach(btn, i % 3, i // 3, 1, 1)
                self.buttons.append(btn)
            root.pack_start(Gtk.Label(label='运行结果（可复制；不会显示密码）', xalign=0), False, False, 0)
            scroller = Gtk.ScrolledWindow()
            scroller.set_hexpand(True)
            scroller.set_vexpand(True)
            root.pack_start(scroller, True, True, 0)
            self.text = Gtk.TextView()
            self.text.set_editable(False)
            self.text.set_cursor_visible(False)
            self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            self.text.modify_font(Pango.FontDescription('monospace 10'))
            scroller.add(self.text)
            self.set_status('status')

        def show_text(self, msg):
            self.text.get_buffer().set_text(msg)

        def confirmation(self, text):
            dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO, text=text)
            response = dialog.run()
            dialog.destroy()
            return response == Gtk.ResponseType.YES

        def ask_secret(self):
            dialog = Gtk.Dialog(title='设置 Borg 仓库密码', transient_for=self,
                flags=Gtk.DialogFlags.MODAL)
            dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '验证并保存', Gtk.ResponseType.OK)
            box = dialog.get_content_area()
            box.set_spacing(8)
            box.set_border_width(12)
            hint = Gtk.Label(label='此密码是现有 Borg 仓库的解密密码，不是系统登录密码。')
            hint.set_line_wrap(True)
            box.pack_start(hint, False, False, 0)
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_placeholder_text('Borg 密码（只输入一次）')
            entry.set_activates_default(True)
            box.pack_start(entry, False, False, 0)
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.show_all()
            accepted = dialog.run() == Gtk.ResponseType.OK
            secret = entry.get_text() if accepted else None
            entry.set_text('')
            dialog.destroy()
            return secret or None

        def set_status(self, command):
            self.start(command, None, silent=True)

        def action(self, widget, command):
            if self.busy:
                return
            secret = None
            if command in ('backup', 'enable', 'disable', 'setup', 'use-existing'):
                names = {'backup':'立即备份并按策略清理旧归档？校验通过后，仅保留最近三个备份日期各一份；其余 mint-* 归档会永久删除。建议先查看清理预览。',
                         'enable':'启用每月备份？错过日期可能立即补执行。成功校验后会永久删除保留策略外的 mint-* 归档；请先查看清理预览。',
                         'setup':'保存密码并启用月度备份？错过日期可能立即运行并按最近三个日期策略删除旧归档。',
                         'use-existing':'复用密码并启用月度备份？可能立即运行并删除保留策略外旧归档。',
                         'disable':'停用每月自动备份并停止正在运行的备份服务？等待 Borg 正常停止后才会报告成功。'}
                if not self.confirmation(names[command]):
                    return
            if command == 'verify-data' and not self.confirmation('深度校验需要读取全部备份数据，可能持续数小时，继续吗？'):
                return
            if command == 'setup':
                secret = self.ask_secret()
                if secret is None:
                    return
            self.start(command, secret)

        def start(self, command, secret, silent=False):
            self.busy = True
            for b in self.buttons:
                b.set_sensitive(False)
            if not silent:
                self.show_text('正在执行 %s …\n' % command)
            def worker():
                argv = ['/usr/bin/homebackup-ext', command]
                try:
                    proc = subprocess.run(argv,
                        input=(secret + '\n') if secret is not None else None,
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        timeout=8*60*60, env={**os.environ, 'LC_ALL':'C.UTF-8'})
                    output = proc.stdout or '(命令没有输出)'
                    ok = proc.returncode == 0
                    if not ok:
                        output += '\n操作失败，退出码：%s。\n' % proc.returncode
                except (OSError, subprocess.TimeoutExpired) as exc:
                    output, ok = '执行失败：%s' % exc, False
                GLib.idle_add(self.finish, command, ok, output, silent)
            threading.Thread(target=worker, daemon=True).start()

        def finish(self, command, ok, output, silent):
            self.busy = False
            for b in self.buttons:
                b.set_sensitive(True)
            if command == 'status':
                self.status.set_text(output.strip() if ok else '状态读取失败：' + output.strip())
            if not silent:
                self.show_text(('完成\n' if ok else '失败\n') + output)
            return False

    window = Window()
    window.show_all()
    if '--smoke-test' in sys.argv:
        GLib.timeout_add(450, Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
