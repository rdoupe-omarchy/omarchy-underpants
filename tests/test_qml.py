import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QmlContractTests(unittest.TestCase):
    def test_launcher_uses_closed_environment(self):
        qml = (ROOT / "Launcher.qml").read_text()
        self.assertIn("clearEnvironment: true", qml)
        self.assertIn('PATH: "/usr/bin:/bin"', qml)
        self.assertIn("function launchEnvironment()", qml)
        self.assertIn('"/usr/bin/python3"', qml)
        self.assertNotIn('["python3"', qml)
        self.assertNotIn('Quickshell.env("PATH")', qml)
        for needle in (
            "PYTHONPATH", "PYTHONHOME", "PYTHONINSPECT", "PYTHONSTARTUP",
            "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT",
        ):
            self.assertNotIn(needle, qml)


class QmlTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("qs"), "Quickshell is not installed")
    def test_payload_reopen_duplicate_and_deferred_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = tmp / "python3"
            shutil.copyfile(ROOT / "tests/fixtures/python3", fake)
            fake.chmod(0o755)
            shutil.copyfile(ROOT / "tests/LauncherTest.qml", tmp / "LauncherTest.qml")
            launcher = (tmp / "Launcher.qml")
            shutil.copyfile(ROOT / "Launcher.qml", launcher)
            launcher.write_text(launcher.read_text().replace('"/usr/bin/python3"', '"' + str(fake) + '"'))
            env = os.environ.copy()
            for key in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
                env.pop(key, None)
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QPA_PLATFORMTHEME="generic", QT_STYLE_OVERRIDE="Fusion",
                       XDG_RUNTIME_DIR=str(tmp), UNDERPANTS_TEST_LOG=str(tmp / "calls"),
                       PATH=str(tmp) + os.pathsep + env["PATH"],
                       PYTHONPATH="/evil/pythonpath", PYTHONHOME="/evil/pythonhome",
                       PYTHONINSPECT="1", LD_PRELOAD="/evil/libpreload.so",
                       LD_LIBRARY_PATH="/evil/lib")
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
            child_env = dict(line.split("=", 1) for line in (tmp / "child-env").read_text().splitlines() if "=" in line)
            self.assertEqual(child_env.get("PATH"), "/usr/bin:/bin")
            self.assertEqual(child_env.get("XDG_RUNTIME_DIR"), str(tmp))
            self.assertEqual(child_env.get("PYTHONPATH"), "UNSET")
            self.assertEqual(child_env.get("PYTHONHOME"), "UNSET")
            self.assertEqual(child_env.get("PYTHONINSPECT"), "UNSET")
            self.assertEqual(child_env.get("LD_PRELOAD"), "UNSET")
            self.assertEqual(child_env.get("LD_LIBRARY_PATH"), "UNSET")
