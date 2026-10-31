#!/usr/bin/env python3
"""Build the complete Mint Toolbox system package, including its Anki importer."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.5.0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir.resolve() / f'mint-toolbox_{VERSION}_all.deb'
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage.chmod(0o755)
        app = stage / 'usr/share/mint-toolbox'
        shutil.copytree(ROOT, app, ignore=shutil.ignore_patterns('dist', 'tests', '__pycache__', '*.pyc', '.git'))
        def write(name, text, mode=0o644):
            file = stage / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding='utf-8')
            file.chmod(mode)
        write('DEBIAN/control', f'''Package: mint-toolbox
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-tk, bash, coreutils, sed, grep, dpkg, apt, pkexec
Recommends: zenity
Description: Unified Linux desktop toolbox and Debian extension manager
 Includes the Anki PDF to WordPress importer, existing local utilities,
 live execution logs, and a ZIP-and-Trash Nemo extension package.
''')
        write('usr/bin/mint-toolbox', '#!/bin/sh\nexec /usr/bin/python3 /usr/share/mint-toolbox/toolbox.py "$@"\n', 0o755)
        write('usr/share/applications/mint-toolbox.desktop', (ROOT / 'packaging/mint-toolbox.desktop').read_text())
        write('usr/share/doc/mint-toolbox/README.md', (ROOT / 'README.md').read_text())
        write('usr/share/doc/mint-toolbox/copyright', 'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2 for the full license.\n')
        for path in sorted(stage.rglob('*'), reverse=True):
            if path.is_dir():
                path.chmod(0o755)
            os.utime(path, (1793404800, 1793404800))
        os.utime(stage, (1793404800, 1793404800))
        subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group',
                        '--build', str(stage), str(output)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': '1793404800'})
    print(output)


if __name__ == '__main__':
    main()
