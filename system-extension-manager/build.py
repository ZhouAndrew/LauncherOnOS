#!/usr/bin/env python3
"""Build the manager and both independently installable system extensions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
from version import VERSION


def build_extensions():
    packages = ROOT / 'packages'
    packages.mkdir(exist_ok=True)
    definitions = [
        dict(id='zip-trash', name='ZIP and Trash', package='mint-toolbox-extension-zip-trash', version='0.4.3',
             description='Nemo right-click ZIP compression, exact-content verification and GIO Trash. Preserves file, directory, dangling and circular symbolic links without following their targets.'),
        dict(id='anki-time-travel', name='Anki Time Travel', package='anki-time-travel', version='0.1.4',
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
    return definitions


def build_manager(output_dir):
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.is_relative_to(ROOT) and output_dir != ROOT / 'dist':
        raise ValueError('Choose an output folder outside the source tree, or use its dist folder')
    definitions = json.loads((ROOT / 'extensions.json').read_text())
    for item in definitions:
        path = ROOT / item['deb']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Bundled extension checksum mismatch: ' + item['id'])
    output = output_dir / f'system-extension-manager_{VERSION}_all.deb'

    output.parent.mkdir(parents=True, exist_ok=True)
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
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build extension packages or optionally package the manager')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--extensions-only', action='store_true', help='rebuild bundled extension debs and their catalog only')
    action.add_argument('--package', action='store_true', help='explicitly build a manager deb without installing it')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist', help='output folder for --package')
    args = parser.parse_args(argv)
    if args.extensions_only:
        build_extensions()
        print('Extension packages and catalog updated. No manager package was built.')
    elif args.package:
        print('Built manager package: ' + str(build_manager(args.output_dir)))
    else:
        parser.print_help()
    return 0


if __name__ == '__main__':
    main()
