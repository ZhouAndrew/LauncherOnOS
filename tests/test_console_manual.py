"""Regression tests for the command console and rendered Markdown manuals."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

SRC = Path(__file__).resolve().parents[1] / "launcheronos.py"


class ConsoleManualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = os.environ.copy()
        self.env["LAUNCHERONOS_HOME"] = str(self.root / "state")
        self.executables = self.root / "executables"
        self.executables.mkdir()
        # Ensure no external renderer is run accidentally.
        self.env["PATH"] = str(self.executables)

    def cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(SRC), *args], env=self.env,
                              input=input, text=True, capture_output=True, timeout=12)

    def sample_zip(self, name="tool.md", content="# Tool\n"):
        archive = self.root / "manuals.zip"
        with ZipFile(archive, "w") as bundle:
            bundle.writestr("LauncherOnOS-manuals/scripts/" + name, content)
            bundle.writestr("LauncherOnOS-manuals/scripts/ignored.sh", "#!/bin/sh\nexit 99\n")
            bundle.writestr("LauncherOnOS-manuals/catalog.json", "{}")
        return archive

    def test_console_is_command_prompt_and_does_not_execute_unknown_command(self):
        result = self.cli(input="help\nlist\nunrecognized\nexit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("launcheronos> ", result.stdout)
        self.assertIn("manual import", result.stdout)
        self.assertIn("Unknown command", result.stdout)
        self.assertNotIn("1 List    2 Search", result.stdout)

    def test_manuals_import_without_installing_scripts(self):
        archive = self.sample_zip()
        result = self.cli("manual", "import", str(archive))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Imported 1", result.stdout)
        self.assertTrue((self.root / "state/manuals/tool.md").is_file())
        self.assertFalse((self.root / "state/manuals/ignored.sh").exists())
        self.assertIn("tool", self.cli("manual", "list").stdout)
        again = self.cli("manual", "import", str(archive))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("Imported 0", again.stdout)

    def test_import_refuses_to_overwrite_modified_manual(self):
        archive = self.sample_zip()
        self.assertEqual(self.cli("manual", "import", str(archive)).returncode, 0)
        (self.root / "state/manuals/tool.md").write_text("keep me", encoding="utf-8")
        result = self.cli("manual", "import", str(archive))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "state/manuals/tool.md").read_text(), "keep me")

    def test_malicious_zip_paths_are_ignored(self):
        archive = self.root / "malicious.zip"
        with ZipFile(archive, "w") as bundle:
            bundle.writestr("scripts/../../bad.md", "# bad")
            bundle.writestr("scripts/good.md", "# Good\n")
        result = self.cli("manual", "import", str(archive))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "state/manuals/good.md").exists())
        self.assertFalse((self.root / "state/bad.md").exists())

    def test_glow_renders_readable_file_not_raw_text(self):
        archive = self.sample_zip(content="# SAMPLE-HEADING\n")
        self.assertEqual(self.cli("manual", "import", str(archive)).returncode, 0)
        glow = self.executables / "glow"
        glow.write_text("#!/bin/sh\nprintf 'RENDERED %s\\n' \"$*\"\n")
        glow.chmod(0o700)
        result = self.cli("manual", "tool")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RENDERED -p", result.stdout)
        self.assertNotIn("SAMPLE-HEADING", result.stdout)

    def test_missing_renderer_reports_install_help_instead_of_raw_markdown(self):
        self.assertEqual(self.cli("manual", "import", str(self.sample_zip())).returncode, 0)
        result = self.cli("manual", "tool")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GlOW".lower(), result.stderr.lower())
        self.assertNotIn("# Tool", result.stdout)

    def test_manuals_work_in_interactive_console(self):
        self.assertEqual(self.cli("manual", "import", str(self.sample_zip())).returncode, 0)
        result = self.cli(input="manual list\nmanual missing\nexit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tool", result.stdout)
        self.assertIn("No manual", result.stderr)


if __name__ == "__main__":
    unittest.main()
