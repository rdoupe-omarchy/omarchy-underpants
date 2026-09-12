"""Descriptor-safe installer publish: no-follow parents, exclusive temps, atomic rename."""
import errno
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("safe_publish", ROOT / "scripts/safe_publish.py")
safe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe)

SAMPLE_TOOLS = {
    "pgrep": "/usr/bin/pgrep",
    "toggle": "/usr/bin/omarchy-toggle-enabled",
    "python3": "/usr/bin/python3",
    "env": "/usr/bin/env",
}


def load_sources():
    return {name: (ROOT / name).read_bytes() for name in safe.PLUGIN_FILES}


def expected_wrapper(home):
    return safe.wrapper_payload(
        screensaver=str(home / safe.PLUGIN_PY_REL),
        **SAMPLE_TOOLS,
    )


class SafePublishTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name) / "test user"
        self.home.mkdir(0o700)
        self.plugin = self.home / safe.PLUGIN_REL
        self.wrapper = self.home / safe.WRAPPER_REL
        self.sources = load_sources()

    def plant_plugin(self):
        self.plugin.mkdir(parents=True)
        for name, data in self.sources.items():
            (self.plugin / name).write_bytes(data)

    def publish_plugin(self, **kwargs):
        kwargs.setdefault("validator", ("true",))
        return safe.publish_plugin(str(ROOT), str(self.home), **kwargs)

    def test_installer_scripts_do_not_use_path_based_writes(self):
        for path in (ROOT / "install.sh", ROOT / "scripts/install-default-screensaver.sh"):
            text = path.read_text()
            self.assertNotIn("mkdir -p", text)
            self.assertNotIn("cat >", text)
            self.assertNotIn("install -m", text)
            self.assertNotIn("chmod +x", text)
            self.assertIn("safe_publish.py", text)
            self.assertIn("underpants_resolve", text)
            self.assertIn("underpants_run", text)
            self.assertNotIn("\npython3 ", text)
            self.assertNotIn("\nomarchy ", text)
            self.assertNotIn("dirname", text)
            self.assertNotIn("\ncat ", text)
            self.assertNotIn("readlink", text)
            self.assertNotIn("\nsleep ", text)
        qml = (ROOT / "Launcher.qml").read_text()
        self.assertIn('"/usr/bin/python3"', qml)
        self.assertNotIn('["python3"', qml)

    def test_open_flags_are_nofollow_exclusive_and_do_not_truncate(self):
        self.assertTrue(safe.DIR_OPEN_FLAGS & os.O_NOFOLLOW)
        self.assertTrue(safe.DIR_OPEN_FLAGS & os.O_DIRECTORY)
        self.assertTrue(safe.FILE_CREATE_FLAGS & os.O_EXCL)
        self.assertTrue(safe.FILE_CREATE_FLAGS & os.O_NOFOLLOW)
        self.assertTrue(safe.FILE_CREATE_FLAGS & os.O_CREAT)
        self.assertFalse(safe.FILE_CREATE_FLAGS & getattr(os, "O_TRUNC", 0))
        self.assertTrue(safe.FILE_PROBE_FLAGS & os.O_NOFOLLOW)
        self.assertFalse(safe.FILE_PROBE_FLAGS & os.O_CREAT)
        self.assertFalse(safe.FILE_PROBE_FLAGS & getattr(os, "O_TRUNC", 0))

    def test_plugin_install_creates_owned_regular_files(self):
        target, backup = self.publish_plugin()
        self.assertIsNone(backup)
        self.assertEqual(target, self.plugin)
        self.assertFalse(self.plugin.is_symlink())
        for name, data in self.sources.items():
            path = self.plugin / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), data)
            info = path.stat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o644)
            self.assertEqual(info.st_nlink, 1)
            self.assertEqual(info.st_uid, os.geteuid())

    def test_wrapper_install_creates_executable_regular_file(self):
        self.plant_plugin()
        path = safe.publish_wrapper(str(self.home), tools=SAMPLE_TOOLS)
        self.assertEqual(path, self.wrapper)
        self.assertFalse(self.wrapper.is_symlink())
        self.assertEqual(self.wrapper.read_bytes(), expected_wrapper(self.home).encode())
        info = self.wrapper.stat()
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o755)
        self.assertEqual(info.st_nlink, 1)
        self.assertEqual(info.st_uid, os.geteuid())

    def test_wrapper_pins_absolute_tools_and_closed_env(self):
        text = expected_wrapper(self.home)
        self.assertIn("pgrep=/usr/bin/pgrep", text)
        self.assertIn("toggle=/usr/bin/omarchy-toggle-enabled", text)
        self.assertIn("python3=/usr/bin/python3", text)
        self.assertIn("env=/usr/bin/env", text)
        self.assertIn("PATH=/usr/bin:/bin", text)
        self.assertIn('"$env" -i', text)
        screensaver = str(self.home / safe.PLUGIN_PY_REL)
        self.assertIn(screensaver, text)
        self.assertNotIn("$HOME/.config/omarchy/plugins", text)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            self.assertFalse(stripped.startswith("pgrep "))
            self.assertFalse(stripped.startswith("python3 "))
            self.assertFalse(stripped.startswith("omarchy-toggle-enabled "))
            self.assertFalse(stripped.startswith("exec python3"))

    def test_resolve_trusted_exec_ignores_ambient_path_shadow(self):
        scratch = Path(self.scratch.name)
        shadow_dir = scratch / "shadow-bin"
        shadow_dir.mkdir()
        shadow = shadow_dir / "python3"
        shadow.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(shadow, 0o755)
        env = os.environ.copy()
        env["PATH"] = str(shadow_dir) + os.pathsep + env.get("PATH", "")
        env.pop("UNDERPANTS_TRUSTED_PATH", None)
        with patch.dict(os.environ, env, clear=True):
            resolved = safe.resolve_trusted_exec("python3")
        self.assertIn(resolved, ("/usr/bin/python3", "/bin/python3"))
        self.assertNotEqual(resolved, str(shadow))

    def test_resolve_trusted_exec_uses_allowlist_and_rejects_symlink_escape(self):
        trusted = Path(self.scratch.name) / "trusted"
        outside = Path(self.scratch.name) / "outside"
        trusted.mkdir()
        outside.mkdir()
        planted = trusted / "omarchy-toggle-enabled"
        planted.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(planted, 0o755)
        env = os.environ.copy()
        env["UNDERPANTS_TRUSTED_PATH"] = str(trusted)
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(safe.resolve_trusted_exec("omarchy-toggle-enabled"), str(planted))
        victim = outside / "evil"
        victim.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(victim, 0o755)
        link = trusted / "eviltool"
        link.symlink_to(victim)
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(safe.PublishError, "trusted eviltool"):
                safe.resolve_trusted_exec("eviltool")

    def test_wrapper_fails_closed_without_trusted_toggle(self):
        self.plant_plugin()
        env = {key: value for key, value in os.environ.items() if key != "UNDERPANTS_TRUSTED_PATH"}
        with patch.dict(os.environ, env, clear=True):
            if os.path.isfile("/usr/bin/omarchy-toggle-enabled") or os.path.isfile("/bin/omarchy-toggle-enabled"):
                self.skipTest("host already has a trusted omarchy-toggle-enabled")
            with self.assertRaisesRegex(safe.PublishError, "trusted omarchy-toggle-enabled"):
                safe.publish_wrapper(str(self.home))

    def test_wrapper_refuses_existing_and_does_not_truncate(self):
        self.plant_plugin()
        self.wrapper.parent.mkdir(parents=True)
        self.wrapper.write_bytes(b"keep-me")
        os.chmod(self.wrapper, 0o644)
        with self.assertRaises(safe.PublishError):
            safe.publish_wrapper(str(self.home), tools=SAMPLE_TOOLS)
        self.assertEqual(self.wrapper.read_bytes(), b"keep-me")

    def test_wrapper_does_not_follow_or_truncate_symlink(self):
        self.plant_plugin()
        victim = Path(self.scratch.name) / "victim"
        victim.write_bytes(b"precious-data")
        self.wrapper.parent.mkdir(parents=True)
        self.wrapper.symlink_to(victim)
        with self.assertRaises(safe.PublishError):
            safe.publish_wrapper(str(self.home), tools=SAMPLE_TOOLS)
        self.assertEqual(victim.read_bytes(), b"precious-data")
        self.assertTrue(self.wrapper.is_symlink())
        self.assertEqual(os.readlink(self.wrapper), str(victim))

    def test_wrapper_refuses_symlink_parents(self):
        self.plant_plugin()
        real = Path(self.scratch.name) / "real-bin"
        real.mkdir(0o755)
        victim = real / safe.WRAPPER_NAME
        victim.write_bytes(b"keep")
        local = self.home / ".local"
        local.mkdir()
        (local / "bin").symlink_to(real)
        with self.assertRaises(safe.PublishError):
            safe.publish_wrapper(str(self.home), tools=SAMPLE_TOOLS)
        self.assertEqual(victim.read_bytes(), b"keep")
        self.assertEqual(list(real.iterdir()), [victim])

    def test_wrapper_refuses_fifo(self):
        self.plant_plugin()
        self.wrapper.parent.mkdir(parents=True)
        os.mkfifo(self.wrapper, 0o644)
        with self.assertRaises(safe.PublishError):
            safe.publish_wrapper(str(self.home), tools=SAMPLE_TOOLS)
        self.assertTrue(stat.S_ISFIFO(os.stat(self.wrapper).st_mode))

    def test_plugin_refuses_existing_without_force(self):
        self.plant_plugin()
        marker = self.plugin / "personal-note.txt"
        marker.write_text("keep this")
        with self.assertRaisesRegex(safe.PublishError, "--force"):
            self.publish_plugin()
        self.assertEqual(marker.read_text(), "keep this")

    def test_plugin_force_backs_up_and_overlays_regular_files(self):
        self.plant_plugin()
        marker = self.plugin / "personal-note.txt"
        marker.write_text("keep this")
        (self.plugin / "README.md").write_text("custom documentation")
        _, message = self.publish_plugin(force=True)
        self.assertIn("underpants-backup.", message)
        backups = list((self.home / ".config/omarchy").glob("underpants-backup.*/plugin"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "README.md").read_text(), "custom documentation")
        self.assertEqual((self.plugin / "README.md").read_bytes(), self.sources["README.md"])
        self.assertEqual(marker.read_text(), "keep this")

    def test_plugin_refuses_symlink_target(self):
        other = self.home / ".config/omarchy/plugins/other"
        other.mkdir(parents=True)
        (other / "README.md").write_text("do-not-touch")
        self.plugin.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(safe.PublishError, "symlink"):
            self.publish_plugin(force=True)
        self.assertEqual((other / "README.md").read_text(), "do-not-touch")
        self.assertTrue(self.plugin.is_symlink())

    def test_plugin_refuses_parent_symlink_and_does_not_write_through(self):
        real = Path(self.scratch.name) / "real-plugins"
        real.mkdir(0o755)
        victim = real / safe.PLUGIN_ID
        victim.mkdir()
        (victim / "README.md").write_text("keep")
        plugins = self.home / ".config/omarchy/plugins"
        plugins.parent.mkdir(parents=True)
        plugins.symlink_to(real)
        with self.assertRaises(safe.PublishError):
            self.publish_plugin(force=True)
        self.assertEqual((victim / "README.md").read_text(), "keep")
        self.assertEqual(list(victim.iterdir()), [victim / "README.md"])

    def test_plugin_refuses_git_managed_target(self):
        self.plant_plugin()
        (self.plugin / ".git").mkdir()
        with self.assertRaisesRegex(safe.PublishError, "Git-managed"):
            self.publish_plugin(force=True)
        (self.plugin / ".git").rmdir()
        (self.plugin / ".git").write_text("file")
        with self.assertRaisesRegex(safe.PublishError, "Git-managed"):
            self.publish_plugin(force=True)

    def test_plugin_refuses_symlink_payload_file_instead_of_truncating(self):
        self.plant_plugin()
        victim = Path(self.scratch.name) / "readme-victim"
        victim.write_bytes(b"precious-readme")
        (self.plugin / "README.md").unlink()
        (self.plugin / "README.md").symlink_to(victim)
        with self.assertRaises(safe.PublishError):
            self.publish_plugin(force=True)
        self.assertEqual(victim.read_bytes(), b"precious-readme")
        self.assertTrue((self.plugin / "README.md").is_symlink())

    def test_publish_file_uses_exclusive_temp_then_atomic_rename(self):
        parent = Path(self.scratch.name) / "parent"
        parent.mkdir(0o700)
        parent_fd = os.open(parent, safe.DIR_OPEN_FLAGS)
        self.addCleanup(os.close, parent_fd)
        safe.publish_file(parent_fd, "dest", b"hello-world", mode=0o644, replace=False)
        dest = parent / "dest"
        self.assertEqual(dest.read_bytes(), b"hello-world")
        leftovers = [path.name for path in parent.iterdir() if path.name != "dest"]
        self.assertEqual(leftovers, [])
        with self.assertRaises(safe.PublishError):
            safe.publish_file(parent_fd, "dest", b"other", mode=0o644, replace=False)
        self.assertEqual(dest.read_bytes(), b"hello-world")

    def test_traverse_rejects_dotdot_and_relative_paths(self):
        with self.assertRaises(safe.PublishError):
            safe._split_abs("relative/home")
        with self.assertRaises(safe.PublishError):
            safe._split_abs("/tmp/../etc")

    def test_rename_noreplace_does_not_replace(self):
        parent = Path(self.scratch.name) / "rename"
        parent.mkdir(0o700)
        (parent / "src").write_bytes(b"new")
        (parent / "dst").write_bytes(b"old")
        parent_fd = os.open(parent, safe.DIR_OPEN_FLAGS)
        self.addCleanup(os.close, parent_fd)
        with self.assertRaises(OSError) as raised:
            safe._rename_noreplace(parent_fd, "src", parent_fd, "dst")
        self.assertIn(raised.exception.errno, (errno.EEXIST, errno.ENOTEMPTY))
        self.assertEqual((parent / "dst").read_bytes(), b"old")
        self.assertEqual((parent / "src").read_bytes(), b"new")


class InstallerScriptTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name) / "script-home"
        self.home.mkdir(0o700)
        self.bin = Path(self.scratch.name) / "trusted-bin"
        self.bin.mkdir()
        toggle = self.bin / "omarchy-toggle-enabled"
        toggle.write_bytes((ROOT / "tests/fixtures/omarchy-toggle-enabled").read_bytes())
        os.chmod(toggle, 0o755)
        self.shadow = Path(self.scratch.name) / "shadow"
        self.shadow.mkdir()
        shadow_python = self.shadow / "python3"
        shadow_python.write_text("#!/bin/bash\nexit 42\n")
        os.chmod(shadow_python, 0o755)
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env["UNDERPANTS_TRUSTED_PATH"] = str(self.bin)
        self.env["PATH"] = str(self.shadow) + os.pathsep + self.env.get("PATH", "")

    def plant_plugin(self):
        plugin = self.home / safe.PLUGIN_REL
        plugin.mkdir(parents=True)
        for name in safe.PLUGIN_FILES:
            (plugin / name).write_bytes((ROOT / name).read_bytes())

    def test_wrapper_script_refuses_symlink_and_prints_nothing_to_victim(self):
        import subprocess
        self.plant_plugin()
        victim = Path(self.scratch.name) / "victim"
        victim.write_bytes(b"still-here")
        wrapper = self.home / safe.WRAPPER_REL
        wrapper.parent.mkdir(parents=True)
        wrapper.symlink_to(victim)
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/install-default-screensaver.sh")],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(victim.read_bytes(), b"still-here")
        self.assertTrue(wrapper.is_symlink())
        self.assertNotIn(f"Wrote {wrapper}", result.stdout)

    def test_wrapper_script_happy_path_uses_trusted_python_and_absolute_tools(self):
        import subprocess
        self.plant_plugin()
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/install-default-screensaver.sh")],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        wrapper = self.home / safe.WRAPPER_REL
        text = wrapper.read_text()
        self.assertIn(safe.resolve_trusted_exec("pgrep"), text)
        self.assertIn(str(self.bin / "omarchy-toggle-enabled"), text)
        self.assertIn(safe.resolve_trusted_exec("python3"), text)
        self.assertIn(safe.resolve_trusted_exec("env"), text)
        self.assertIn('"$env" -i', text)
        self.assertIn("PATH=/usr/bin:/bin", text)
        self.assertIn(str(self.home / safe.PLUGIN_PY_REL), text)
        self.assertIn(f"Wrote {wrapper}", result.stdout)
        self.assertIn("fixed absolute launcher", result.stdout)
        self.assertNotIn("export PATH=", result.stdout)
        self.assertNotIn("PREPEND", result.stdout)
        self.assertNotIn("Legacy PATH-override wrapper still present", result.stdout)

    def test_wrapper_script_reports_legacy_path_override(self):
        import subprocess
        self.plant_plugin()
        legacy = self.home / ".local/bin/omarchy-launch-screensaver"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"keep-legacy")
        os.chmod(legacy, 0o644)
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/install-default-screensaver.sh")],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(legacy.read_bytes(), b"keep-legacy")
        self.assertIn(str(legacy), result.stdout)
        self.assertIn("Legacy PATH-override wrapper still present", result.stdout)
        self.assertTrue((self.home / safe.WRAPPER_REL).is_file())

    def test_idle_docs_prefer_absolute_path_over_path_selection(self):
        readme = (ROOT / "README.md").read_text()
        installer = (ROOT / "scripts/install-default-screensaver.sh").read_text()
        self.assertNotIn("export PATH=", readme)
        self.assertNotIn("PREPEND", readme)
        self.assertNotIn("export PATH=", installer)
        self.assertNotIn("dirname", installer)
        self.assertNotIn("\ncat ", installer)
        self.assertIn("underpants-launch-screensaver", readme)
        self.assertIn("omarchy-launch-screensaver", readme)
        self.assertIn("fixed absolute", readme.lower() + installer.lower())


if __name__ == "__main__":
    unittest.main()
