#!/usr/bin/env python3
"""Build the manager and both independently installable system extensions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
VERSION = '0.1.0'


def main():
    packages = ROOT / 'packages'
    packages.mkdir(exist_ok=True)
    definitions = [
        dict(id='zip-trash', name='ZIP and Trash', package='mint-toolbox-extension-zip-trash', version='0.4.2',
             description='Nemo right-click ZIP compression, exact-content verification and GIO Trash. Preserves file, directory, dangling and circular symbolic links without following their targets.'),
        dict(id='anki-time-travel', name='Anki Time Travel', package='anki-time-travel', version='0.1.3',
             launch=['/usr/bin/anki-time-travel', '--gui'],
             description='Import historical Anki PDF statistics into local WordPress, with a CLI, file chooser and live logs. Preserves historical dates and verifies imported posts, attachments and the exact post permalink. Requires WP-CLI and an accessible existing WordPress site.')
    ]
    for item in definitions:
        source = ROOT / 'sources' / item['id']
        subprocess.run([sys.executable, str(source / 'build.py'), '--output-dir', str(packages)], check=True)
        deb = packages / f'{item["package"]}_{item["version"]}_all.deb'
        item['deb'] = str(deb.relative_to(ROOT))
        item['sha256'] = hashlib.sha256(deb.read_bytes()).hexdigest()
        files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix != '.pyc')
        item['source'] = dict(kind='bundled', requires=['python3', 'dpkg-deb', 'xz'],
            files={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            argv=['python3', f'sources/{item["id"]}/build.py', '--output-dir', '{output}'])
    (ROOT / 'extensions.json').write_text(json.dumps(definitions, indent=2) + '\n')
    output = ROOT / 'dist' / f'system-extension-manager_{VERSION}_all.deb'
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage.chmod(0o755)
        shutil.copytree(ROOT, stage / 'usr/share/system-extension-manager',
                        ignore=shutil.ignore_patterns('dist', 'tests', '__pycache__', '*.pyc'))
        def write(path, text, mode=0o644):
            path = stage / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            path.chmod(mode)
        write('DEBIAN/control', f'''Package: system-extension-manager
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-tk, dpkg, apt, pkexec
Description: Manage independent system extensions through Debian packages
 Provides multiple-extension listing, install/remove controls, verified source
 builds, application launching, live logs, and bundled Anki and ZIP extensions.
''')
        write('usr/bin/system-extension-manager', '#!/bin/sh\nexec /usr/bin/python3 /usr/share/system-extension-manager/manager.py "$@"\n', 0o755)
        write('usr/share/applications/system-extension-manager.desktop', (ROOT / 'system-extension-manager.desktop').read_text())
        write('usr/share/doc/system-extension-manager/README.md', (ROOT / 'README.md').read_text())
        write('usr/share/doc/system-extension-manager/copyright', 'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2.\n')
        for path in sorted(stage.rglob('*'), reverse=True):
            if path.is_dir():
                path.chmod(0o755)
            os.utime(path, (1793404800, 1793404800))
        os.utime(stage, (1793404800, 1793404800))
        subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group', '--build', str(stage), str(output)],
                       check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '1793404800'})
    print(output)


if __name__ == '__main__':
    main()
