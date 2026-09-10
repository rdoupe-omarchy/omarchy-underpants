import fcntl
import importlib.util
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import tempfile
import time
import unittest
import unicodedata

SOURCE = Path(__file__).resolve().parents[1] / "screensaver.py"
spec = importlib.util.spec_from_file_location("screensaver", SOURCE)
saver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(saver)


class StoryTests(unittest.TestCase):
    def test_story_and_cycle(self):
        for seconds, expected in ((0, "boxers. briefs. knickers."), (9, "consider this a heist."), (22, "anyone remember step two?"), (25, "2. ???")):
            frame = "\n".join(saver.scene(seconds).lines())
            self.assertIn(expected, frame)
            for label in ("1. COLLECT UNDERPANTS", "2. ???", "3. PROFIT!"):
                self.assertEqual(frame.count(label), 1)
            for spoiler in ("wonderful", "earnest", "BUILD COOL STUFF", "better computers", "everyone", "including the gnomes"):
                self.assertNotIn(spoiler, frame)
        self.assertEqual(saver.scene(0).lines(), saver.scene(saver.CYCLE).lines())

    def test_profit_reveal_and_readable_hold(self):
        opening = "\n".join(saver.scene(26).lines())
        self.assertIn("3. PROFIT!", opening)
        self.assertNotIn("including the gnomes.", opening)
        for seconds in (36, 38, 41, 44):
            lines = saver.scene(seconds, 137, 32).lines()
            self.assertIn("including the gnomes.", "\n".join(lines))
            # Coin fountains must leave both complete headline lines readable.
            for y, text in ((4, "BETTER COMPUTERS"), (9, "FOR EVERYONE")):
                lettering = saver.block_letters(text)
                x = (137 - len(lettering[0])) // 2
                for row, expected in enumerate(lettering):
                    self.assertEqual(lines[y + row][x:x + len(expected)], expected)
        self.assertNotEqual(saver.scene(28).lines(), saver.scene(30).lines())

    def test_phase_boxes_and_animated_thoughts(self):
        for seconds, label in ((9, "1. COLLECT UNDERPANTS"), (24, "2. ???"), (40, "3. PROFIT!")):
            lines = saver.scene(seconds, 137, 32).lines()
            y = next(y for y, line in enumerate(lines) if label in line)
            x = lines[y].index(label) - 2
            self.assertEqual(lines[y][x:x + len(label) + 4], "║ " + label + " ║")
            self.assertEqual(lines[y - 1][x:x + len(label) + 4], "╔" + "═" * (len(label) + 2) + "╗")
            self.assertEqual(lines[y + 1][x:x + len(label) + 4], "╚" + "═" * (len(label) + 2) + "╝")
        a, b = saver.Canvas(20, 12), saver.Canvas(20, 12)
        saver.question_mark(a, 5, 3, 31, 0)
        saver.question_mark(b, 5, 3, 31.5, 0)
        self.assertNotEqual(a.lines(), b.lines())
        self.assertNotIn("?", "".join(a.lines()))
        self.assertGreater(sum(c != " " for line in a.lines() for c in line), 8)

    def test_zen_is_animated_and_has_no_story_text(self):
        frames = [saver.scene(t, 137, 32, "zen") for t in (0, 0.5, 7, 14.9, 15, 30, 10000)]
        for frame in frames:
            plain = "".join(frame.lines())
            self.assertFalse(any(c.isalpha() or c in "?.$!" for c in plain))
            self.assertTrue(any(c in "█▀▄" for c in plain))
        self.assertNotEqual(frames[0].cells, frames[1].cells)
        self.assertNotEqual(frames[0].cells, frames[4].cells)
        # Each lane regenerates on its own 15-second cycle, never a story reset.
        for t in (0, 15, 30):
            lines = saver.scene(t + 1, 137, 32, "zen").lines()
            self.assertIn("████████", lines[14])

    def test_zen_cli_and_sizes(self):
        output = subprocess.check_output([sys.executable, str(SOURCE), "--mode", "zen", "--frame", "10"], text=True)
        self.assertNotIn("COLLECT", output)
        self.assertNotIn("PROFIT", output)
        for width, height in ((1, 1), (40, 15), (100, 26), (137, 32), (320, 120)):
            lines = saver.scene(8, width, height, "zen").lines()
            self.assertEqual(len(lines), height)
            self.assertTrue(all(len(line) == width for line in lines))

    def test_large_creed_stays_readable_with_coins(self):
        for width, height, messages in (
            (137, 32, ((15, "BE EARNEST."), (20, "BE SINCERE."), (25, "BE BRAVE."))),
            (100, 30, ((14, "BE EARNEST."), (19, "BE SINCERE."), (24, "BE BRAVE."))),
            (160, 50, ((27, "BE EARNEST. BE SINCERE."), (32, "BE BRAVE."))),
        ):
            lines = saver.scene(46, width, height).lines()
            for y, text in messages:
                lettering = saver.block_letters(text)
                x = (width - len(lettering[0])) // 2
                for row, expected in enumerate(lettering):
                    self.assertEqual(lines[y + row][x:x + len(expected)], expected)

    def test_coins_move_and_end_before_reset(self):
        frames = []
        for seconds in (1.2, 1.3, 1.5, 27):
            canvas = saver.Canvas(137, 32)
            saver.gold_coins(canvas, seconds, 3)
            frames.append("\n".join(canvas.lines()))
        self.assertFalse(frames[0].strip())
        self.assertIn("$", frames[1])
        self.assertNotEqual(frames[1], frames[2])
        self.assertFalse(frames[3].strip())

    def test_laundry_leaves_logo_one_pair_at_a_time(self):
        for seconds, remaining in ((2.5, 3), (7.4, 2), (12.9, 1), (18.3, 0)):
            lines = saver.scene(seconds, saver.LOGO_WIDTH, 26).lines()
            # After its entrance the wordmark remains fully legible.
            logo_row = [line.rstrip() for line in lines].index(saver.LOGO[2])
            self.assertEqual(lines[logo_row + 8].count("████████"), remaining)

    def test_sizes_and_single_cell_text(self):
        for width, height in ((1, 1), (40, 15), (80, 30), (100, 36), (160, 50), (320, 120)):
            for seconds in (0, 4, 11, 17, 24, 35, 37, 43, 47, 56, 10000):
                lines = saver.scene(seconds, width, height).lines()
                self.assertEqual(len(lines), height)
                self.assertTrue(all(len(line) == width for line in lines))
                self.assertTrue(all(unicodedata.east_asian_width(c) not in "WF" and not unicodedata.combining(c)
                                    for line in lines for c in line))

    def test_every_frame_of_story_and_two_zen_cycles(self):
        for mode, seconds in (("story", saver.CYCLE + 1), ("zen", 31)):
            for frame in range(seconds * 12):
                canvas = saver.scene(frame / 12, 137, 32, mode)
                lines = canvas.lines(True)
                self.assertEqual(len(lines), 32)
                self.assertTrue(all(line.endswith("\x1b[0m") for line in lines))


class TerminalTests(unittest.TestCase):
    def run_terminal(self, action, mode="story", extra=()):
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 100, 0, 0))
        process = subprocess.Popen([sys.executable, str(SOURCE), "--mode", mode, *extra], stdin=slave, stdout=slave, stderr=slave)
        output = b""
        try:
            deadline = time.monotonic() + 5
            acted = False
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    output += os.read(master, 65536)
                if not acted and (b"COLLECT UNDERPANTS" in output if mode == "story" else b"\x1b[?2026l" in output):
                    action(process, master, slave)
                    acted = True
                if process.poll() is not None:
                    while select.select([master], [], [], 0)[0]:
                        output += os.read(master, 65536)
                    break
            self.assertTrue(acted, output[-1000:])
            self.assertEqual(process.poll(), 0, output[-1000:])
            self.assertEqual(termios.tcgetattr(slave), before)
            self.assertIn(b"\x1b[?1049l", output)
            self.assertNotIn(b"Traceback", output)
            return output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_key_dismiss_and_terminal_restore(self):
        self.run_terminal(lambda process, master, slave: os.write(master, b"x"))

    def test_signal_dismiss_and_terminal_restore(self):
        self.run_terminal(lambda process, master, slave: process.send_signal(signal.SIGTERM))

    def test_zen_dismiss_and_terminal_restore(self):
        self.run_terminal(lambda process, master, slave: os.write(master, b"x"), "zen")

    def test_duration_exit_and_preview_mouse_reporting(self):
        output = self.run_terminal(lambda *args: None, "zen", ("--preview", "--duration", "0.2"))
        self.assertNotIn(b"\x1b[?1003h", output)
        self.assertNotIn(b"\x1b[?1006h", output)

    def test_shared_stop_dismisses_and_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / "stop"
            self.run_terminal(lambda *args: stop.touch(), "story", ("--stop-file", str(stop)))

    def test_mouse_dismisses_after_startup_grace(self):
        def move(process, master, slave):
            time.sleep(0.9)
            os.write(master, b"\x1b[<35;10;10M")
        self.run_terminal(move)

    def test_resize_and_dismiss(self):
        def resize(process, master, slave):
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 16, 50, 0, 0))
            time.sleep(0.15)
            os.write(master, b"\x1b")
        self.run_terminal(resize)


if __name__ == "__main__":
    unittest.main()
