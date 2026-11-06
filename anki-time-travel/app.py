#!/usr/bin/python3
"""Compatibility entry point; the implementation belongs to Mint Toolbox."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
if not (ROOT / 'anki_import.py').is_file():
    sys.path.insert(0, str(ROOT.parent / 'mint-toolbox'))
import anki_import
if __name__ == '__main__':
    sys.exit(anki_import.main())
