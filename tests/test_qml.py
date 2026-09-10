import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("qs"), "Quickshell is not installed")
    def test_payload_reopen_duplicate_and_deferred_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = tmp / "python3"
            shutil.copyfile(ROOT / "tests/fixtures/python3", fake)
            fake.chmod(0o755)
            shutil.copyfile(ROOT / "tests/LauncherTest.qml", tmp / "LauncherTest.qml")
            shutil.copyfile(ROOT / "Launcher.qml", tmp / "Launcher.qml")
            env = os.environ.copy()
            for key in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
                env.pop(key, None)
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QPA_PLATFORMTHEME="generic", QT_STYLE_OVERRIDE="Fusion",
                       XDG_RUNTIME_DIR=str(tmp), UNDERPANTS_TEST_LOG=str(tmp / "calls"),
                       PATH=str(tmp) + os.pathsep + env["PATH"])
            result = subprocess.run([shutil.which("qs"), "-p", str(tmp / "LauncherTest.qml")],
                                    capture_output=True, text=True, env=env, timeout=10)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("LAUNCHER_TEST_PASS", output)
            self.assertNotIn("BAD_", output)
            self.assertNotIn("TEST_TIMEOUT", output)
            calls = (tmp / "calls").read_text().splitlines()
            self.assertEqual(len(calls), 3, calls)
            self.assertEqual([call.rsplit(" ", 1)[-1] for call in calls], ["zen", "story", "zen"])
