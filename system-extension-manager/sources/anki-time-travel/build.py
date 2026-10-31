#!/usr/bin/env python3
"""Build the independently installable Anki Time Travel extension."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PACKAGE = 'anki-time-travel'
VERSION = '0.1.3'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir.resolve() / f'{PACKAGE}_{VERSION}_all.deb'
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage.chmod(0o755)
        def write(path, data, mode=0o644):
            path = stage / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding='utf-8')
            path.chmod(mode)
        write('DEBIAN/control', f'''Package: {PACKAGE}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: bash, coreutils, sed, grep, python3 (>= 3.10), python3-tk
Description: Anki PDF to WordPress system extension
 Provides a CLI and desktop window for verified historical PDF imports.
 Requires a configured local WordPress site and WP-CLI installed separately.
''')
        write('usr/bin/anki-time-travel', '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/anki-time-travel/app.py "$@"\n', 0o755)
        for name in ['app.py', 'execution.py', 'anki-time-travel.sh']:
            write('usr/lib/anki-time-travel/' + name, (ROOT / name).read_text(), 0o755 if name.endswith('.sh') else 0o644)
        write('usr/share/applications/anki-time-travel.desktop', (ROOT / 'anki-time-travel.desktop').read_text())
        write('usr/share/doc/anki-time-travel/copyright', 'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2.\n')
        for path in sorted(stage.rglob('*'), reverse=True):
            os.utime(path, (1793404800, 1793404800))
        os.utime(stage, (1793404800, 1793404800))
        subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group', '--build', str(stage), str(output)],
                       check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '1793404800'})
    print(output)


if __name__ == '__main__':
    main()
