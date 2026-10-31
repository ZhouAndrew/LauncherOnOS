#!/usr/bin/env python3
"""Build the bundled, architecture-independent Nemo extension reproducibly."""
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
package = 'mint-toolbox-extension-zip-trash'
version = '0.3.0'
output = root / 'debs' / f'{package}_{version}_all.deb'
output.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    stage = Path(tmp)
    stage.chmod(0o755)
    def write(path, text):
        file = stage / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        file.chmod(0o644)
    write('DEBIAN/control', f'''Package: {package}
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: python3 (>= 3.10), zip, unzip, libglib2.0-bin, zenity, nemo
Description: Mint Toolbox verified ZIP and Trash Nemo action
 Compress selected local files to ZIP using system utilities, verify contents,
 then move original files to the desktop Trash.
''')
    write('usr/bin/mint-toolbox-zip-trash', (root / 'zip_trash.py').read_text())
    (stage / 'usr/bin/mint-toolbox-zip-trash').chmod(0o755)
    write('usr/share/nemo/actions/mint-toolbox-zip-trash.nemo_action',
          (root / 'packaging/zip-trash.nemo_action').read_text())
    write(f'usr/share/doc/{package}/copyright', 'Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2 for the full license.\n')
    for path in sorted(stage.rglob('*'), reverse=True):
        os.utime(path, (1793404800, 1793404800))
    os.utime(stage, (1793404800, 1793404800))
    subprocess.run(['dpkg-deb', '-Zxz', '-z6', '--threads-max=1', '--root-owner-group', '--build', str(stage), str(output)],
                   check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '1793404800'})
manifest = [{
    'id': 'zip-trash', 'name': '压缩为 ZIP 并删除', 'package': package, 'version': version,
    'deb': 'debs/' + output.name,
    'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
    'description': 'Nemo 原生右键菜单，支持同目录多选文件和文件夹。调用系统 zip / unzip，逐项校验内容并确认原文件未变化，再通过 GIO 移入回收站。不会覆盖已有 ZIP；失败不执行永久删除。暂不支持符号链接及特殊文件。安装后重新打开文件管理器窗口；如菜单未刷新，可注销后重新登录。'
}]
(root / 'system-plugins.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
