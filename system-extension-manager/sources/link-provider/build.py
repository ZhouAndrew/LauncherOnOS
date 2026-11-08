#!/usr/bin/env python3
"""Build the independently installable Link Provider extension."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PACKAGE = "mint-link-provider-extension"
VERSION = "0.2.2"
EPOCH = 1793404800


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve() / f"{PACKAGE}_{VERSION}_all.deb"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        control = stage / "DEBIAN/control"
        control.parent.mkdir()
        control.write_text(f"""Package: {PACKAGE}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ZhouAndrew <zhouandrew@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, libglib2.0-bin, desktop-file-utils
Description: Manage desktop links and fixed local commands
 Provides a standalone GTK window and a command-line interface for creating
 links to user-configured programs and URLs, with optional user-level
 caldav-run protocol registration.
""", encoding="utf-8")

        files = {
            "link-provider": "usr/lib/mint-link-provider/link-provider",
            "link_provider_gui.py": "usr/lib/mint-link-provider/link_provider_gui.py",
            "mint-link-provider.desktop": "usr/share/applications/mint-link-provider.desktop",
            "README.md": f"usr/share/doc/{PACKAGE}/README.md",
        }
        for name, relative in files.items():
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
            destination.chmod(0o755 if name == "link-provider" else 0o644)
        copyright_path = stage / f"usr/share/doc/{PACKAGE}/copyright"
        copyright_path.write_text(
            "Copyright: 2026 ZhouAndrew\nLicense: GPL-2\n See /usr/share/common-licenses/GPL-2.\n",
            encoding="utf-8",
        )
        launcher = stage / "usr/bin/link-provider"
        launcher.parent.mkdir()
        launcher.symlink_to("../lib/mint-link-provider/link-provider")

        for path in [*sorted(stage.rglob("*"), reverse=True), stage]:
            if path.is_dir():
                path.chmod(0o755)
            os.utime(path, (EPOCH, EPOCH), follow_symlinks=False)
        subprocess.run(
            ["dpkg-deb", "-Zxz", "-z6", "--threads-max=1", "--root-owner-group",
             "--build", str(stage), str(output)],
            env={**os.environ, "SOURCE_DATE_EPOCH": str(EPOCH)},
            check=True,
        )
    print(output)


if __name__ == "__main__":
    main()
