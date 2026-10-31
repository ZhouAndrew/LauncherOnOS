#!/usr/bin/env python3
"""Build the standalone, system-installable Anki Time Travel Debian package."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
VERSION = '0.1.2'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir.resolve() / f'anki-time-travel_{VERSION}_all.deb'
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage.chmod(0o755)
        def write(name, data, mode=0o644):
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding='utf-8')
            path.chmod(mode)
        write('DEBIAN/control', f'''Package: anki-time-travel
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: bash, coreutils, sed, grep, python3 (>= 3.10), python3-tk
Description: Historical Anki PDF import into local WordPress
 Provides CLI and desktop file selection, historical timestamps and
 verified WordPress post and attachment imports. Requires a configured local
 WordPress site and WP-CLI installed separately.
''')
        write('usr/bin/anki-time-travel', '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/anki-time-travel/app.py "$@"\n', 0o755)
        write('usr/lib/anki-time-travel/app.py', (ROOT / 'app.py').read_text())
        write('usr/lib/anki-time-travel/execution.py', (ROOT.parent / 'mint-toolbox/execution.py').read_text())
        write('usr/lib/anki-time-travel/anki-time-travel.sh', (ROOT.parent / 'mint-toolbox/originals/anki-time-travel.sh').read_text(), 0o755)
        write('usr/share/applications/anki-time-travel.desktop', (ROOT / 'anki-time-travel.desktop').read_text())
        write('usr/share/doc/anki-time-travel/README.md', (ROOT / 'README.md').read_text())
        write('usr/share/doc/anki-time-travel/copyright', 'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2 for the full license.\n')
        for path in sorted(stage.rglob('*'), reverse=True):
            os.utime(path, (1793404800, 1793404800))
        os.utime(stage, (1793404800, 1793404800))
        subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group',
                        '--build', str(stage), str(output)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': '1793404800'})
    print(output)


if __name__ == '__main__':
    main()
