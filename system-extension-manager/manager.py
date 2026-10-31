#!/usr/bin/python3
"""Manage independent system extensions using their bundled Debian packages."""
import argparse
import sys
from pathlib import Path
import subprocess
import lifecycle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', action='store_true', help='open the extension manager')
    ops = parser.add_mutually_exclusive_group()
    ops.add_argument('--build-package', action='store_true', help='optionally build a manager deb; does not install it')
    parser.add_argument('--output-dir', type=Path, default=Path.cwd() / 'dist', help='output folder for --build-package')
    ops.add_argument('--list', action='store_true', help='list extensions and actual package states')
    choices = [row['id'] for row in lifecycle.plugins()]
    ops.add_argument('--enable', metavar='ID', choices=choices, help='install the bundled extension deb')
    ops.add_argument('--disable', metavar='ID', choices=choices, help='uninstall the extension package')
    ops.add_argument('--build', metavar='ID', choices=choices, help='build pinned sources as a regular user, then install')
    ops.add_argument('--open', metavar='ID', choices=choices, help='open an installed extension application')
    args = parser.parse_args(argv)
    try:
        if args.build_package:
            lifecycle.build_manager_package(args.output_dir)
        elif args.list:
            for row in lifecycle.plugins():
                print(row['id'], row['name'], lifecycle.state_text(row['package']), sep='\t')
        elif args.enable:
            lifecycle.change(args.enable, True)
        elif args.disable:
            lifecycle.change(args.disable, False)
        elif args.build:
            lifecycle.change(args.build, True, from_source=True)
        elif args.open:
            lifecycle.open_extension(args.open)
        else:
            lifecycle.show_gui()
        return 0
    except ImportError as exc:
        print('Error: GUI support is unavailable. Install python3-tk to use the desktop window. ' + str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('Error:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
