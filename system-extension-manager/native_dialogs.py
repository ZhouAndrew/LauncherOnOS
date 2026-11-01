"""Prefer the desktop GTK file chooser; retain Tk as a fallback."""
import json
import subprocess

_SCRIPT = '''
import gi, json, sys
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
options=json.loads(sys.argv[1])
action={'open':Gtk.FileChooserAction.OPEN,'directory':Gtk.FileChooserAction.SELECT_FOLDER,'save':Gtk.FileChooserAction.SAVE}[options['kind']]
dialog=Gtk.FileChooserNative.new(options['title'],None,action,None,None)
dialog.set_select_multiple(options['multiple'])
if options['kind']=='save': dialog.set_do_overwrite_confirmation(True)
for label,pattern in options.get('filetypes',[]):
    item=Gtk.FileFilter(); item.set_name(label); item.add_pattern(pattern); dialog.add_filter(item)
result=dialog.run()
print(json.dumps(dialog.get_filenames() if result==Gtk.ResponseType.ACCEPT else []))
dialog.destroy()
'''


def _choose(kind, multiple=False, **kwargs):
    options = dict(kind=kind, multiple=multiple, title=kwargs.get('title', 'Select a file'),
                   filetypes=kwargs.get('filetypes', []))
    try:
        result = subprocess.run(['/usr/bin/python3', '-c', _SCRIPT, json.dumps(options)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            paths = json.loads(result.stdout)
            return tuple(paths) if multiple else (paths[0] if paths else '')
    except (OSError, ValueError):
        pass
    from tkinter import filedialog
    callback = filedialog.askdirectory if kind == 'directory' else filedialog.asksaveasfilename if kind == 'save' else filedialog.askopenfilenames
    return callback(**kwargs)


def askdirectory(**kwargs):
    return _choose('directory', **kwargs)


def askopenfilenames(**kwargs):
    return _choose('open', multiple=True, **kwargs)


def asksaveasfilename(**kwargs):
    return _choose('save', **kwargs)
