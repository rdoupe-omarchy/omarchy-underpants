import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = shutil.which("omarchy-plugin-validate") or str(ROOT / "tests/fixtures/omarchy-plugin-validate")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.tmp = Path(self.scratch.name)
        self.home = self.tmp / "test user"
        self.home.mkdir()
        self.target = self.home / ".config/omarchy/plugins/douper.underpants"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name in ("omarchy", "omarchy-shell"):
            dest = self.bin / name
            shutil.copyfile(ROOT / "tests/fixtures" / name, dest)
            dest.chmod(0o755)
        self.shadow = self.tmp / "shadow"
        self.shadow.mkdir()
        for name in ("omarchy", "omarchy-shell", "python3"):
            dest = self.shadow / name
            dest.write_text('#!/bin/bash\nprintf "SHADOW %s\\n" "$0" >> "$UNDERPANTS_TEST_LOG"\nexit 42\n')
            dest.chmod(0o755)
        self.env = os.environ.copy()
        # Fixture home only; never invoke the real shell IPC or user installer.
        # Ambient PATH is poisoned; only the allowlisted trusted bin is used.
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.tmp / "unused-config"),
                        UNDERPANTS_TEST_LOG=str(self.tmp / "calls"),
                        UNDERPANTS_TEST_VALIDATOR=VALIDATOR,
                        UNDERPANTS_TRUSTED_PATH=str(self.bin),
                        PATH=str(self.shadow) + os.pathsep + str(self.bin) + os.pathsep + self.env["PATH"])

    def install(self, *args):
        return subprocess.run(["bash", str(ROOT / "install.sh"), *args], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_clean_install_has_no_implicit_activation(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("manifest.json", "Launcher.qml", "screensaver.py", "README.md", "LICENSE", "menu-entries.json"):
            self.assertEqual((ROOT / name).read_bytes(), (self.target / name).read_bytes())
        calls = (self.tmp / "calls").read_text()
        self.assertNotIn("enable", calls)
        self.assertNotIn("rescanPlugins", calls)
        self.assertNotIn("SHADOW", calls)
        self.assertFalse((self.tmp / "unused-config").exists())
        self.assertFalse((self.home / ".config/omarchy/shell.json").exists())

    def test_missing_trusted_omarchy_fails_closed_and_ignores_path_shadow(self):
        if any(os.path.isfile(os.path.join(directory, "omarchy")) for directory in ("/usr/bin", "/bin")):
            self.skipTest("host already has a trusted omarchy")
        env = self.env.copy()
        env.pop("UNDERPANTS_TRUSTED_PATH", None)
        result = subprocess.run(["bash", str(ROOT / "install.sh")], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trusted omarchy", result.stderr)
        self.assertFalse(self.target.exists())
        log = self.tmp / "calls"
        self.assertFalse(log.exists() and "SHADOW" in log.read_text())

    def test_reinstall_requires_consent_and_makes_backup(self):
        self.assertEqual(self.install().returncode, 0)
        marker = self.target / "personal-note.txt"
        marker.write_text("keep this")
        old = self.target / "README.md"
        old.write_text("custom documentation")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(old.read_text(), "custom documentation")
        result = self.install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list((self.home / ".config/omarchy").glob("underpants-backup.*/plugin"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "README.md").read_text(), "custom documentation")
        self.assertEqual(marker.read_text(), "keep this")

    def test_explicit_enable_uses_scoped_ipc(self):
        self.assertEqual(self.install("--enable").returncode, 0)
        calls = (self.tmp / "calls").read_text()
        self.assertIn("shell rescanPlugins", calls)
        self.assertIn("plugin enable douper.underpants", calls)

    def test_git_and_symlink_targets_are_not_overwritten(self):
        self.assertEqual(self.install().returncode, 0)
        (self.target / ".git").mkdir()
        self.assertNotEqual(self.install("--force").returncode, 0)
        (self.target / ".git").rmdir()
        other = self.target.with_name("other")
        self.target.rename(other)
        self.target.symlink_to(other, target_is_directory=True)
        self.assertNotEqual(self.install("--force").returncode, 0)

    def test_unknown_option_does_not_write(self):
        self.assertEqual(self.install("--typo").returncode, 2)
        self.assertFalse(self.target.exists())

    def test_parent_symlink_is_not_followed(self):
        real = self.tmp / "real-plugins"
        real.mkdir()
        victim = real / "douper.underpants"
        victim.mkdir()
        (victim / "README.md").write_text("keep")
        plugins = self.home / ".config/omarchy/plugins"
        plugins.parent.mkdir(parents=True)
        plugins.symlink_to(real)
        result = self.install("--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((victim / "README.md").read_text(), "keep")
        self.assertEqual(list(victim.iterdir()), [victim / "README.md"])
