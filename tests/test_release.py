"""Release checks: CLI boundaries, compositor isolation and packaged metadata."""
import argparse
import json
import os
import select
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_screensaver import SOURCE, saver

ROOT = SOURCE.parent


class ReleaseTests(unittest.TestCase):
    def test_manifest_and_menu_contract(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["id"], "douper.underpants")
        self.assertEqual(manifest["kinds"], ["overlay"])
        self.assertFalse(manifest["id"].startswith("omarchy."))
        for path in manifest["entryPoints"].values():
            self.assertNotIn("..", path)
            self.assertFalse(Path(path).is_absolute())
            self.assertTrue((ROOT / path).is_file())
        entries = json.loads((ROOT / "menu-entries.json").read_text())
        self.assertEqual(len(entries), 2)
        self.assertIn('"mode":"story"', entries["system.underpants"]["action"])
        self.assertIn('"mode":"zen"', entries["system.underpants-zen"]["action"])
        self.assertIn("David Heinemeier Hansson", (ROOT / "LICENSE").read_text())

    def test_invalid_cli_inputs_fail_cleanly(self):
        for args in (("--mode", "nope"), ("--frame", "nan"), ("--offset", "inf"),
                     ("--duration", "-1"), ("--frame", "0", "--width", "0"),
                     ("--frame", "0", "--height", "121")):
            result = subprocess.run([sys.executable, str(SOURCE), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, args)
            self.assertNotIn("Traceback", result.stderr)

    def test_nonterminal_usage_fails_cleanly(self):
        result = subprocess.run([sys.executable, str(SOURCE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Run inside a terminal", result.stderr)

    def test_terminal_arguments_preserve_paths_and_mode(self):
        runner = ["python3", "/a path/screensaver.py", "--mode", "zen"]
        with patch.dict(os.environ, {"OMARCHY_PATH": "/an omarchy path"}):
            for terminal in ("foot.desktop", "Alacritty.desktop", "com.mitchellh.ghostty.desktop", "kitty.desktop"):
                command = saver.terminal_command(terminal, runner)
                self.assertEqual(command[-len(runner):], runner)
                self.assertTrue(any(saver.APP_ID in arg for arg in command))
            with self.assertRaises(RuntimeError):
                saver.terminal_command("xterm", runner)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "OMARCHY_PATH"):
            saver.terminal_command("foot", runner)

    def test_launch_on_two_monitors_and_owned_cleanup(self):
        for mode in ("story", "zen"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as runtime:
                args = argparse.Namespace(terminal="foot", preview=True, offset=4, duration=9, mode=mode)
                monitors = [{"name": "A", "id": 0, "focused": True}, {"name": "B", "id": 1}]
                children = []

                def spawn(command, **kwargs):
                    self.assertTrue(callable(kwargs["preexec_fn"]))
                    child = Mock()
                    child.command = command
                    child.poll.return_value = None
                    children.append(child)
                    return child

                def hypr(*args, **kwargs):
                    if args[0] == "monitors":
                        return monitors
                    if args[0] == "clients":
                        return [{"class": saver.APP_ID, "monitor": n} for n in range(len(children))]
                    if args[0] == "activewindow":
                        return {"class": "another.app"}
                    self.fail(args)

                with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": "/omarchy"}), \
                     patch.object(saver, "hypr", side_effect=hypr), \
                     patch.object(saver, "focus_monitor") as focus, \
                     patch.object(saver.subprocess, "Popen", side_effect=spawn), \
                     patch.object(saver.time, "sleep"):
                    saver.launch(args)
                self.assertEqual(focus.call_args_list, [(("A",),), (("B",),), (("A",),)])
                self.assertEqual(len(children), 2)
                for child in children:
                    command = child.command
                    self.assertEqual(command[command.index("--mode") + 1], mode)
                    self.assertIn("--preview", command)
                    self.assertEqual(command[command.index("--duration") + 1], "9")
                    child.terminate.assert_called_once()
                    child.wait.assert_called_once_with(timeout=3)
                self.assertEqual(len(list(Path(runtime).iterdir())), 1)  # lock only, no stale stop/session

    def test_startup_failure_cleans_up_child(self):
        with tempfile.TemporaryDirectory() as runtime:
            args = argparse.Namespace(terminal="foot", preview=False, offset=0, duration=0, mode="story")
            child = Mock()
            child.poll.return_value = 1
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": "/omarchy"}), \
                 patch.object(saver, "hypr", side_effect=[[{"name": "A", "id": 0}], [], []]), \
                 patch.object(saver, "focus_monitor"), \
                 patch.object(saver.subprocess, "Popen", return_value=child), \
                 self.assertRaisesRegex(RuntimeError, "exited during startup"):
                saver.launch(args)
            child.wait.assert_called_once_with(timeout=3)
            self.assertEqual(len(list(Path(runtime).iterdir())), 1)

    def test_existing_screensaver_prevents_launch(self):
        with patch.object(saver, "hypr", side_effect=[[], [{"class": saver.APP_ID}]]), \
             patch.object(saver.subprocess, "Popen") as spawn:
            saver.launch(argparse.Namespace())
            spawn.assert_not_called()

    def test_owned_child_exits_if_launcher_is_killed(self):
        code = (
            "import sys, subprocess; "
            "sys.path.insert(0, sys.argv[1]); import screensaver; "
            "child = subprocess.Popen(['sleep', '30'], preexec_fn=screensaver.owned_terminal_setup()); "
            "print(child.pid, flush=True); child.wait()"
        )
        supervisor = subprocess.Popen([sys.executable, "-c", code, str(ROOT)], stdout=subprocess.PIPE, text=True)
        fd = None
        try:
            self.assertTrue(select.select([supervisor.stdout], [], [], 5)[0])
            child_pid = int(supervisor.stdout.readline())
            fd = os.pidfd_open(child_pid)
            supervisor.kill()
            supervisor.wait(timeout=5)
            self.assertTrue(select.select([fd], [], [], 5)[0], "Owned child outlived its launcher")
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait()
            if fd is not None:
                if not select.select([fd], [], [], 0)[0]:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                os.close(fd)
            supervisor.stdout.close()


if __name__ == "__main__":
    unittest.main()
