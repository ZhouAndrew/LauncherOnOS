# Combined Arms 1.08.2 — DD / DD2 radar + Mirage tank (incremental patch)

This package contains **an installer script**, not a replacement copy of the entire YAML mod.
It patches the locally installed YAML in place so your previous air/naval/self-repair edits are retained.

## Changes

- Allies DD (Destroyer): mobile 12-cell radar.
- GDI DD2 (Frigate): Mobile Sensor Array-equivalent radar, 24-cell tracking, 10-cell cloak detection and 12-cell allied ground-vision support. Existing DD2 MSAR settings are kept unchanged.
- England RTNK (Mirage Tank): faster disguise recovery, 175% ambush damage, a new **MirageHeatRA2** weapon (7900 base damage, increased effectiveness vs infantry and armor, 44 tick reload, 5-cell range).
- Other users of **120mmHEAT** are unchanged.
- Original anti-submarine, naval weapons and existing aircraft rules remain untouched.

## Install on Linux Mint

1. Quit Combined Arms.
2. Extract this ZIP.
3. Run this command from the folder containing install.py:

   python3 install.py

The installer compares your Desktop copy with the installed game files, aborts on differences,
backs up originals and creates ~/Desktop/CombinedArms-1.08.2-DD-DD2-Mirage-Changed-Only.zip
containing ONLY YAML files changed during that run.

**Important:** if you already installed DD2 MSAR as in the previous task, the installer
recognizes that configuration and preserves it rather than adding duplicates.

It has not been run on your actual Linux Mint system. ZIP integrity checks are not game engine tests.
