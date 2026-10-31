#!/usr/bin/env python3
"""Build the Nemo extension and its pinned, local source recipe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'mint-toolbox-extension-zip-trash'
VERSION = '0.4.0'
SOURCES = ['zip_trash.py', 'execution.py', 'packaging/build.py', 'packaging/zip-trash.nemo_action']


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
        write('usr/lib/mint-toolbox/execution.py', (ROOT / 'execution.py').read_text())
        write('usr/share/nemo/actions/mint-toolbox-zip-trash.nemo_action',
              (ROOT / 'packaging/zip-trash.nemo_action').read_text())
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
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'debs')
    parser.add_argument('--package-only', action='store_true', help='do not update the application catalog')
    args = parser.parse_args()
    output = build(args.output_dir.resolve())
    if not args.package_only:
        manifest = [{
            'id': 'zip-trash', 'name': 'Compress to ZIP and delete', 'package': PACKAGE, 'version': VERSION,
            'deb': str(output.relative_to(ROOT)),
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'description': 'Native Nemo context-menu action for local files and folders. Uses system zip/unzip, verifies archive contents and original files, then moves originals to Trash through GIO. Supports multiple selections and collision-safe filenames. Symbolic links and special files are not supported. Commands and output remain visible in a log window.',
            'source': {
                'kind': 'bundled',
                'requires': ['python3', 'dpkg-deb', 'xz'],
                'files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
                'argv': ['python3', 'packaging/build.py', '--package-only', '--output-dir', '{output}']
            }
        }]
        (ROOT / 'system-plugins.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built package: ' + str(output))


if __name__ == '__main__':
    main()
