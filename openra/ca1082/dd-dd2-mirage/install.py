#!/usr/bin/env python3
# OpenRA Combined Arms 1.08.2 - incremental DD/DD2 radar and Mirage Tank update.
# Uses Python standard library only. Does not replace unrelated rules.
from pathlib import Path
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED
import os
import re
import shutil
import stat
import sys

HOME = Path.home()
SOURCE = HOME / "Desktop/CombinedArms-1.08.2-Latest-Verified-Rules/mods/ca"
GAME = (HOME / "Documents/shared/App/Game/CombinedArms-1.08.2-x86_64/"
        "CombinedArms-1.08 (nx).2-navalfix-x86_64-app-image/"
        "usr/lib/openra/mods/ca")
FILES = ["rules/ships.yaml", "rules/vehicles.yaml", "weapons/ballistics.yaml"]
OUTPUT = HOME / "Desktop/CombinedArms-1.08.2-DD-DD2-Mirage-Changed-Only.zip"
BACKUP = HOME / "Documents/OpenRA-rules-backups" / (
    "DD-DD2-Mirage-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))

ALLIED_RADAR = (
    "\tProvidesRadar:\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\tRangedGpsRadarProvider:\n"
    "\t\tRange: 12c0\n"
    "\t\tTargetTypes: Vehicle, Air, Structure, Ship\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\tWithDetectionCircle:\n"
    "\t\tRange: 12c0\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
)
GDI_MSAR = (
    "\tProvidesRadar:\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\tRangedGpsRadarProvider:\n"
    "\t\tRange: 24c0\n"
    "\t\tTargetTypes: Vehicle, Air, Structure\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\tWithDetectionCircle:\n"
    "\t\tRange: 24c0\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\t\tTrailCount: 3\n"
    "\tDetectCloaked@SENSORARRAY:\n"
    "\t\tRange: 10c0\n"
    "\t\tDetectionTypes: Cloak, AirCloak\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\tProximityExternalCondition@Bino:\n"
    "\t\tCondition: bino\n"
    "\t\tRange: 12c0\n"
    "\t\tEnableSound: dsaping1.aud\n"
    "\t\tAffectsParent: False\n"
    "\t\tRequiresCondition: !(empdisable || being-warped)\n"
    "\tExternalCondition@JAMMED:\n"
    "\t\tCondition: jammed\n"
    "\tProvidesPrerequisite@radar-active:\n"
    "\t\tPrerequisite: radar-active\n"
    "\t\tRequiresCondition: !(jammed || empdisable || being-warped)\n"
)
MIRAGE_WEAPON = (
    "MirageHeatRA2:\n"
    "\tInherits: 120mmHEAT\n"
    "\tReloadDelay: 44\n"
    "\tRange: 5c0\n"
    "\tWarhead@1Dam: SpreadDamage\n"
    "\t\tDamage: 7900\n"
    "\t\tVersus:\n"
    "\t\t\tNone: 100\n"
    "\t\t\tWood: 40\n"
    "\t\t\tLight: 125\n"
    "\t\t\tHeavy: 90\n"
    "\t\t\tConcrete: 25\n"
    "\t\t\tBrick: 25\n\n"
)

def actor_span(text, actor):
    matches = list(re.finditer(
        rf"(?m)^{re.escape(actor)}:[ \t]*$", text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {actor} actor; found {len(matches)}")
    begin = matches[0].start()
    tail = re.search(r"(?m)^[A-Za-z0-9^._-]+:[ \t]*$", text[matches[0].end():])
    end = matches[0].end() + tail.start() if tail else len(text)
    return begin, end, text[begin:end]

def replace_actor(text, actor, change):
    begin, end, block = actor_span(text, actor)
    return text[:begin] + change(block) + text[end:]

def add_after_shroud(block, extra, actor):
    anchor = "\tRevealsShroud@GAPGEN:\n\t\tRange: 5c0\n"
    if block.count(anchor) != 1:
        raise RuntimeError(f"{actor}: unexpected shroud configuration")
    return block.replace(anchor, anchor + extra, 1)

def has_trait(block, trait):
    return re.search(rf"(?m)^\t{re.escape(trait)}:[ \t]*$", block) is not None

def patch_allied(block):
    radar_names = ("ProvidesRadar", "RangedGpsRadarProvider", "WithDetectionCircle")
    present = [has_trait(block, x) for x in radar_names]
    if all(present):
        if ("\tRangedGpsRadarProvider:\n\t\tRange: 12c0\n" not in block or
            "\tProvidesRadar:\n" not in block):
            raise RuntimeError("DD has different radar settings; manual review required")
        return block
    if any(present):
        raise RuntimeError("DD has a partial radar config; refusing to overwrite")
    return add_after_shroud(block, ALLIED_RADAR, "DD")

def patch_gdi(block):
    names = ("ProvidesRadar", "RangedGpsRadarProvider", "WithDetectionCircle",
             "DetectCloaked@SENSORARRAY", "ProximityExternalCondition@Bino")
    present = [has_trait(block, x) for x in names]
    if all(present):
        if ("\tRangedGpsRadarProvider:\n\t\tRange: 24c0\n" not in block or
            "\tDetectCloaked@SENSORARRAY:\n\t\tRange: 10c0\n" not in block or
            "\tProximityExternalCondition@Bino:\n\t\tCondition: bino\n\t\tRange: 12c0\n" not in block):
            raise RuntimeError("DD2 has non-matching sensor array; manual review required")
        return block
    if any(present):
        raise RuntimeError("DD2 has a partial sensor array; refusing to overwrite")
    return add_after_shroud(block, GDI_MSAR, "DD2")

def trait_value(block, trait, field, old, new):
    # Only touch a named trait inside the RTNK actor.
    pattern = re.compile(rf"(?m)^\t{re.escape(trait)}:[ \t]*$")
    found = list(pattern.finditer(block))
    if len(found) != 1:
        raise RuntimeError(f"RTNK missing or ambiguous trait: {trait}")
    p = found[0]
    next_trait = re.search(r"(?m)^\t[A-Za-z0-9@._-]+:[ \t]*$", block[p.end():])
    end = p.end() + next_trait.start() if next_trait else len(block)
    part = block[p.start():end]
    old_line = f"\t\t{field}: {old}\n"
    new_line = f"\t\t{field}: {new}\n"
    if old_line in part:
        if part.count(old_line) != 1:
            raise RuntimeError(f"RTNK duplicate property {trait}.{field}")
        part = part.replace(old_line, new_line, 1)
    elif new_line not in part:
        raise RuntimeError(f"RTNK unexpected {trait}.{field} value")
    return block[:p.start()] + part + block[end:]

def patch_mirage(block):
    block = trait_value(block, "Armament", "Weapon", "120mmHEAT", "MirageHeatRA2")
    block = trait_value(block, "Mirage", "InitialDelay", "99", "35")
    block = trait_value(block, "Mirage", "RevealDelay", "100", "55")
    block = trait_value(block, "Cloak@NORMAL", "InitialDelay", "99", "35")
    block = trait_value(block, "Cloak@NORMAL", "CloakDelay", "100", "55")
    block = trait_value(block, "FirepowerMultiplier@Ambush", "Modifier", "150", "175")
    # Maintain the vulnerable / ambush-oriented Red Alert 2 role, not an invulnerable tank.
    weaknesses = r"• Weak vs Defenses, Infantry\n• Cannot attack Aircraft"
    new_weaknesses = r"• Weak vs Defenses\n• Cannot attack Aircraft"
    if weaknesses in block:
        block = block.replace(weaknesses, new_weaknesses, 1)
    strengths = "• Strong vs Light Armor, Heavy Armor"
    if strengths in block:
        block = block.replace(strengths,
                              "• Strong vs Infantry, Light Armor, Heavy Armor", 1)
    return block

def patch_ships(text):
    text = replace_actor(text, "DD", patch_allied)
    return replace_actor(text, "DD2", patch_gdi)

def patch_vehicles(text):
    return replace_actor(text, "RTNK", patch_mirage)

def patch_ballistics(text):
    if re.search(r"(?m)^MirageHeatRA2:[ \t]*$", text):
        _, _, existing = actor_span(text, "MirageHeatRA2")
        if existing.strip() != MIRAGE_WEAPON.strip():
            raise RuntimeError("MirageHeatRA2 already exists with different parameters")
        return text
    _, end, _ = actor_span(text, "120mmHEAT")
    return text[:end] + MIRAGE_WEAPON + text[end:]

PATCHERS = {"rules/ships.yaml": patch_ships,
            "rules/vehicles.yaml": patch_vehicles,
            "weapons/ballistics.yaml": patch_ballistics}

def write_atomic(path, data):
    temporary = path.with_name(path.name + f".patch-{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

def main():
    print("OpenRA Combined Arms 1.08.2 - DD / DD2 Radar + Mirage Tank")
    original = {}
    proposed = {}
    changed = []
    # Verify both installed trees match before touching any file.
    for relative in FILES:
        a, b = SOURCE / relative, GAME / relative
        for path in (a, b):
            if not path.is_file() or path.is_symlink():
                raise RuntimeError(f"Missing file or symlink: {path}")
        sa, sb = a.read_bytes(), b.read_bytes()
        if sa != sb:
            raise RuntimeError(f"Desktop/game mismatch: {relative}; stopped safely")
        if b"\r\n" in sa:
            raise RuntimeError(f"Windows CRLF unsupported in {relative}")
        original[relative] = sa
        patched = PATCHERS[relative](sa.decode("utf-8")).encode("utf-8")
        proposed[relative] = patched
        if patched != sa:
            changed.append(relative)

    if not changed:
        print("PASS: All three files already contain the requested changes.")
        return

    BACKUP.mkdir(parents=True, exist_ok=False)
    for relative in changed:
        for name, root in (("desktop", SOURCE), ("game", GAME)):
            target = BACKUP / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
    print("PASS: Pre-change backup:", BACKUP)

    modified_paths = []
    temporary_zip = OUTPUT.with_name(OUTPUT.name + ".tmp")
    try:
        for relative in changed:
            for root in (SOURCE, GAME):
                path = root / relative
                write_atomic(path, proposed[relative])
                modified_paths.append((path, original[relative]))
        for relative in changed:
            assert (SOURCE / relative).read_bytes() == proposed[relative]
            assert (GAME / relative).read_bytes() == proposed[relative]

        with ZipFile(temporary_zip, "w", ZIP_DEFLATED) as z:
            for relative in changed:
                z.writestr("mods/ca/" + relative, proposed[relative])
        with ZipFile(temporary_zip) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(changed)
        os.replace(temporary_zip, OUTPUT)
    except BaseException:
        for path, data in reversed(modified_paths):
            try:
                write_atomic(path, data)
            except OSError as error:
                print("ROLLBACK FAILED:", path, error, file=sys.stderr)
        raise
    finally:
        if temporary_zip.exists():
            temporary_zip.unlink()

    print("PASS: Desktop and game files synchronized")
    print("Files updated:", ", ".join(changed))
    print("Changed-rules ZIP:", OUTPUT)
    print("Backup:", BACKUP)
    print("NOTE: Game loading and combat behavior have not been tested.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
