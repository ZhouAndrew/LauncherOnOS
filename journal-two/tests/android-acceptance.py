#!/usr/bin/env python3
"""Drive the installed app through Android's editor and document picker."""
import hashlib
from pathlib import Path
import re
import subprocess
import time
from xml.etree import ElementTree
from zipfile import ZipFile

APP = "io.github.zhouandrew.journaltwo"
ACTIVITY = f"{APP}/org.qosp.notes.ui.launcher.LauncherActivity"
OUT = Path("journal-acceptance")
OUT.mkdir(exist_ok=True)


def adb(*args):
    return subprocess.check_output(["adb", *args])


def shell(*args):
    return adb("shell", *args)


def tree():
    path = "/sdcard/journal-ui.xml"
    for _ in range(5):
        shell("rm", "-f", path)
        shell("uiautomator", "dump", path)
        try:
            return ElementTree.fromstring(shell("cat", path))
        except (subprocess.CalledProcessError, ElementTree.ParseError):
            time.sleep(2)
    raise AssertionError("Android UI hierarchy was unavailable after repeated attempts")


def find(*labels, scroll=False):
    for _ in range(8):
        root = tree()
        nodes = list(root.iter("node"))
        dismiss = next((n for n in nodes if n.get("resource-id") == "android:id/aerr_close"), None)
        if dismiss is not None and any("Launcher isn't responding" in n.get("text", "") for n in nodes):
            click(dismiss)
            launch()
            continue
        for node in nodes:
            values = [node.get(k, "") for k in ("text", "content-desc", "resource-id")]
            if any(label in values or any(v.endswith("/" + label) for v in values)
                   for label in labels):
                return node
        if scroll:
            shell("input", "swipe", "225", "320", "225", "90", "300")
        time.sleep(1)
    (OUT / "last-ui.xml").write_bytes(ElementTree.tostring(root))
    (OUT / "last-screen.png").write_bytes(adb("exec-out", "screencap", "-p"))
    raise AssertionError(f"Cannot find {labels}")


def tap(*labels, scroll=False):
    click(find(*labels, scroll=scroll))


def click(node):
    left, top, right, bottom = map(int, re.findall(r"\d+", node.get("bounds")))
    shell("input", "tap", str((left + right) // 2), str((top + bottom) // 2))
    time.sleep(0.7)


def launch():
    shell("am", "start", "-W", "-a", "android.intent.action.MAIN",
          "-c", "android.intent.category.LAUNCHER", "-n", ACTIVITY)
    time.sleep(5)


def overflow():
    if any("inputmethod" in n.get("package", "") for n in tree().iter("node")):
        shell("input", "keyevent", "KEYCODE_BACK")
    tap("More options")


def attach(name):
    overflow()
    tap("Attach files", scroll=True)
    try:
        tap(name)
    except AssertionError:
        tap("Show roots", "Show root list", "Open navigation drawer")
        tap("Downloads")
        tap(name)
    time.sleep(2)


def text(value):
    shell("input", "text", value)
    time.sleep(0.5)


try:
    # Known synthetic originals. GPS is injected through the Android emulator.
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=red:s=128x96", "-frames:v", "1", "-threads", "1",
                    str(OUT / "journal-photo.png")], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=s=160x120:r=24:d=8", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", str(OUT / "journal-video.mp4")], check=True)
    for name in ("journal-photo.png", "journal-video.mp4"):
        adb("push", str(OUT / name), "/sdcard/Download/" + name)
        shell("am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
              "-d", "file:///sdcard/Download/" + name)
    shell("pm", "grant", APP, "android.permission.ACCESS_COARSE_LOCATION")
    shell("pm", "grant", APP, "android.permission.ACCESS_FINE_LOCATION")
    launch()
    tap("edit_text_title")
    text("JournalTwoAcceptance")
    tap("edit_text_content")
    text("FIRST")
    attach("journal-photo.png")
    text("BETWEEN")
    attach("journal-video.mp4")
    text("AFTER")
    tap("Add current location")
    for _ in range(4):
        adb("emu", "geo", "fix", "115.86", "-31.95")
        time.sleep(1)
    shell("am", "force-stop", APP)
    launch()
    find("JournalTwoAcceptance")
    tap("Play video", scroll=True)
    time.sleep(2)
    (OUT / "inline-video.png").write_bytes(adb("exec-out", "screencap", "-p"))
    activities = shell("dumpsys", "activity", "activities").decode()
    assert any("topResumedActivity" in line and "MainActivity" in line
               for line in activities.splitlines()), activities
    assert "MediaActivity" not in "\n".join(
        line for line in activities.splitlines() if "topResumedActivity" in line
    )
    overflow()
    tap("Export for WordPress", scroll=True)
    tap("Save", "button1")
    time.sleep(2)
    for folder in ("Download", "Documents"):
        try:
            adb("pull", f"/sdcard/{folder}/JournalTwoAcceptance.html.zip",
                str(OUT / "android-export.html.zip"))
            break
        except subprocess.CalledProcessError:
            continue
    with ZipFile(OUT / "android-export.html.zip") as archive:
        body = archive.read("note.html").decode()
        expected = ["FIRST", "<img", "BETWEEN", "<video", "AFTER", "openstreetmap.org"]
        assert sorted(expected, key=body.index) == expected, body
        for entry, name in (("attachments/1.png", "journal-photo.png"),
                            ("attachments/2.mp4", "journal-video.mp4")):
            original = (OUT / name).read_bytes()
            assert archive.read(entry) == original
            print(entry, hashlib.sha256(original).hexdigest())
    print("PASS: Android editor, force-stop/reopen, in-place player action, location, export")
except Exception:
    (OUT / "logcat.txt").write_bytes(adb("logcat", "-d", "-t", "1800"))
    raise
