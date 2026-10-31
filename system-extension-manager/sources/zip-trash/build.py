#!/usr/bin/env python3
"""Build the Nemo extension and its pinned, local source recipe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PACKAGE = 'mint-toolbox-extension-zip-trash'
VERSION = '0.4.2'
SOURCES = ['zip_trash.py', 'execution.py', 'build.py', 'zip-trash.nemo_action']


def build(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f'{PACKAGE}_{VERSION}_all.deb'
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage.chmod(0o755)
        def write(path, text, mode=0o644):
            file = stage / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding='utf-8')
            file.chmod(mode)
        write('DEBIAN/control', f'''Package: {PACKAGE}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-tk, zip, unzip, libglib2.0-bin, nemo
Description: Mint Toolbox verified ZIP and Trash Nemo action
 Compress selected local files using system utilities and verify the archive
 before moving originals to Trash. Shows live commands and saves operation logs.
''')
        write('usr/bin/mint-toolbox-zip-trash', (ROOT / 'zip_trash.py').read_text(), 0o755)
        write('usr/lib/system-extensions/zip-trash/execution.py', (ROOT / 'execution.py').read_text())
        write('usr/share/nemo/actions/mint-toolbox-zip-trash.nemo_action',
              (ROOT / 'zip-trash.nemo_action').read_text())
        write(f'usr/share/doc/{PACKAGE}/copyright',
              'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2 for the full license.\n')
        for path in sorted(stage.rglob('*'), reverse=True):
            os.utime(path, (1793404800, 1793404800))
        os.utime(stage, (1793404800, 1793404800))
        subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group',
                        '--build', str(stage), str(output)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': '1793404800'})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output_dir.resolve()))


if __name__ == '__main__':
    main()
