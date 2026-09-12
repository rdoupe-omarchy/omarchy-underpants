"""Release checks: CLI boundaries, compositor isolation and packaged metadata."""
import argparse
import json
import os
import select
import signal
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_screensaver import SOURCE, saver

ROOT = SOURCE.parent


def assert_only_private_lock_remains(test, runtime):
    entries = list(Path(runtime).iterdir())
    test.assertEqual([path.name for path in entries], [saver.RUNTIME_SUBDIR])
    private = entries[0]
    test.assertTrue(private.is_dir())
    test.assertFalse(private.is_symlink())
    test.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o700)
    leftover = list(private.iterdir())
    test.assertEqual(len(leftover), 1, leftover)
    test.assertTrue(leftover[0].is_file())
    test.assertFalse(leftover[0].is_symlink())
    test.assertEqual(leftover[0].stat().st_nlink, 1)
    test.assertEqual(leftover[0].stat().st_uid, os.geteuid())


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

                with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": "/omarchy",
                                             "HYPRLAND_INSTANCE_SIGNATURE": "testhipr"}), \
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
                assert_only_private_lock_remains(self, runtime)

    def test_startup_failure_cleans_up_child(self):
        with tempfile.TemporaryDirectory() as runtime:
            args = argparse.Namespace(terminal="foot", preview=False, offset=0, duration=0, mode="story")
            child = Mock()
            child.poll.return_value = 1
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": "/omarchy",
                                         "HYPRLAND_INSTANCE_SIGNATURE": "testhipr"}), \
                 patch.object(saver, "hypr", side_effect=[[{"name": "A", "id": 0}], [], []]), \
                 patch.object(saver, "focus_monitor"), \
                 patch.object(saver.subprocess, "Popen", return_value=child), \
                 self.assertRaisesRegex(RuntimeError, "exited during startup"):
                saver.launch(args)
            child.wait.assert_called_once_with(timeout=3)
            assert_only_private_lock_remains(self, runtime)

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

    def test_run_capped_rejects_oversized_stdout(self):
        over = saver.PRODUCER_STDOUT_MAX + 1
        with self.assertRaisesRegex(RuntimeError, "oversized"):
            saver.run_capped([sys.executable, "-c", f"import sys; sys.stdout.write('x' * {over})"], timeout=5)

    def test_lock_open_flags_are_nofollow_exclusive_and_do_not_truncate(self):
        self.assertTrue(saver.LOCK_CREATE_FLAGS & os.O_EXCL)
        self.assertTrue(saver.LOCK_CREATE_FLAGS & os.O_NOFOLLOW)
        self.assertTrue(saver.LOCK_CREATE_FLAGS & os.O_CREAT)
        self.assertTrue(saver.LOCK_CREATE_FLAGS & os.O_RDWR)
        self.assertFalse(saver.LOCK_CREATE_FLAGS & getattr(os, "O_TRUNC", 0))
        self.assertTrue(saver.LOCK_REOPEN_FLAGS & os.O_NOFOLLOW)
        self.assertTrue(saver.LOCK_REOPEN_FLAGS & os.O_RDWR)
        self.assertFalse(saver.LOCK_REOPEN_FLAGS & getattr(os, "O_TRUNC", 0))
        self.assertFalse(saver.LOCK_REOPEN_FLAGS & os.O_CREAT)
        self.assertTrue(saver.DIR_OPEN_FLAGS & os.O_NOFOLLOW)
        self.assertTrue(saver.DIR_OPEN_FLAGS & os.O_DIRECTORY)

    def test_session_lock_creates_private_owned_regular_file(self):
        with tempfile.TemporaryDirectory() as runtime:
            env = {"XDG_RUNTIME_DIR": runtime, "HYPRLAND_INSTANCE_SIGNATURE": "testhipr"}
            with patch.dict(os.environ, env):
                with saver.session_lock() as state_dir:
                    private = Path(runtime) / saver.RUNTIME_SUBDIR
                    self.assertTrue(os.path.samefile(state_dir, private))
                    self.assertEqual(state_dir, Path("/proc/self/fd") / os.path.basename(state_dir))
                    lock = state_dir / saver.session_lock_name()
                    self.assertTrue(lock.is_file())
                    self.assertFalse(lock.is_symlink())
                    info = lock.stat()
                    self.assertTrue(stat.S_ISREG(info.st_mode))
                    self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
                    self.assertEqual(info.st_nlink, 1)
                    self.assertEqual(info.st_uid, os.geteuid())
                    with saver.session_lock() as busy:
                        self.assertIsNone(busy)

    def test_lock_does_not_follow_or_truncate_symlink(self):
        with tempfile.TemporaryDirectory() as runtime:
            private = Path(runtime) / saver.RUNTIME_SUBDIR
            private.mkdir(0o700)
            victim = Path(runtime) / "victim"
            victim.write_bytes(b"precious-data")
            planted = private / "default.lock"
            planted.symlink_to(victim)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "HYPRLAND_INSTANCE_SIGNATURE": "default"}):
                with self.assertRaises(RuntimeError):
                    with saver.session_lock():
                        pass
            self.assertEqual(victim.read_bytes(), b"precious-data")
            self.assertTrue(planted.is_symlink())
            self.assertEqual(os.readlink(planted), str(victim))

    def test_lock_rejects_runtime_and_private_dir_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir(0o700)
            link = Path(tmp) / "link"
            link.symlink_to(real)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(link), "HYPRLAND_INSTANCE_SIGNATURE": "default"}):
                with self.assertRaises(RuntimeError):
                    with saver.session_lock():
                        pass
            self.assertEqual(list(real.iterdir()), [])

            runtime = Path(tmp) / "runtime"
            runtime.mkdir(0o700)
            private = runtime / saver.RUNTIME_SUBDIR
            private.symlink_to(real)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime), "HYPRLAND_INSTANCE_SIGNATURE": "default"}):
                with self.assertRaises(RuntimeError):
                    with saver.session_lock():
                        pass
            self.assertEqual(list(real.iterdir()), [])

    def test_lock_rejects_nonregular_world_accessible_and_hardlinked_files(self):
        with tempfile.TemporaryDirectory() as runtime:
            private = Path(runtime) / saver.RUNTIME_SUBDIR
            private.mkdir(0o700)
            fifo = private / "default.lock"
            os.mkfifo(fifo, 0o600)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "HYPRLAND_INSTANCE_SIGNATURE": "default"}):
                with self.assertRaises(RuntimeError):
                    with saver.session_lock():
                        pass
            fifo.unlink()

            os.chmod(runtime, 0o777)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "HYPRLAND_INSTANCE_SIGNATURE": "default"}):
                with self.assertRaises(RuntimeError):
                    with saver.session_lock():
                        pass
            os.chmod(runtime, 0o700)

            lock = private / "default.lock"
            lock.write_bytes(b"")
            os.chmod(lock, 0o600)
            extra = Path(runtime) / "hardlink"
            os.link(lock, extra)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "HYPRLAND_INSTANCE_SIGNATURE": "default"}):
                with self.assertRaises(RuntimeError):
                    with saver.session_lock():
                        pass
            extra.unlink()

    def test_missing_or_relative_runtime_dir_fails_closed(self):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": ""}, clear=False):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            with self.assertRaisesRegex(RuntimeError, "XDG_RUNTIME_DIR"):
                with saver.session_lock():
                    pass
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": "relative/runtime"}):
            with self.assertRaisesRegex(RuntimeError, "XDG_RUNTIME_DIR"):
                with saver.session_lock():
                    pass
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "../escape"}):
            with self.assertRaisesRegex(RuntimeError, "instance signature"):
                saver.session_lock_name()

    def test_busy_lock_skips_launch_without_spawning(self):
        with tempfile.TemporaryDirectory() as runtime:
            env = {"XDG_RUNTIME_DIR": runtime, "OMARCHY_PATH": "/omarchy",
                   "HYPRLAND_INSTANCE_SIGNATURE": "testhipr"}
            with patch.dict(os.environ, env), saver.session_lock() as held:
                self.assertIsNotNone(held)
                with patch.object(saver, "hypr", side_effect=[[{"name": "A", "id": 0, "focused": True}], []]), \
                     patch.object(saver.subprocess, "Popen") as spawn:
                    saver.launch(argparse.Namespace(terminal="foot", preview=False, offset=0, duration=0, mode="story"))
                    spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
