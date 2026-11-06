#!/usr/bin/env python3
"""Build the manual security-updates system extension without installing it."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PACKAGE = 'mint-security-updates-extension'
VERSION = '0.1.0'
EPOCH = 1793404800


def build(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f'{PACKAGE}_{VERSION}_all.deb'
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage.chmod(0o755)

        def write(name, content, mode=0o644):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            target.chmod(mode)

        write('DEBIAN/control', f'''Package: {PACKAGE}
Version: {VERSION}
Section: admin
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-apt, python3-tk, apt, dpkg, pkexec, psmisc
Description: Opt-in Ubuntu security updates with kernel and NVIDIA protection
 Only explicitly requested security updates are installed after APT simulation.
 Does not install timers, enable automatic upgrades or schedule reboots.
''')
        write('usr/lib/mint-security-updates/security_updates.py',
              (ROOT / 'security_updates.py').read_text())
        write('usr/bin/mint-security-updates',
              '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/mint-security-updates/security_updates.py "$@"\n', 0o755)
        write('usr/share/applications/mint-security-updates.desktop',
              (ROOT / 'security-updates.desktop').read_text())
        write(f'usr/share/doc/{PACKAGE}/copyright',
              'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2.\n')
        for path in sorted(stage.rglob('*'), reverse=True):
            os.utime(path, (EPOCH, EPOCH))
        os.utime(stage, (EPOCH, EPOCH))
        subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1',
                        '--root-owner-group', '--build', str(stage), str(output)],
                       check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': str(EPOCH)})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output_dir.resolve()))


if __name__ == '__main__':
    main()
