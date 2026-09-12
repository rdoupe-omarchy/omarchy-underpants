#!/usr/bin/python3
"""Underpants Gnomes: a silent, text-only Omarchy screensaver."""

import argparse
import contextlib
import ctypes
import fcntl
import json
import math
import os
from pathlib import Path
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import termios
import time
import tty

APP_ID = "org.omarchy.screensaver"
RUNTIME_SUBDIR = "douper.underpants"
PRODUCER_STDOUT_MAX = 2 * 1024 * 1024
PRODUCER_STDERR_MAX = 64 * 1024
DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
LOCK_CREATE_FLAGS = (
    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
)
LOCK_REOPEN_FLAGS = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
HEIST_END = 21
PROFIT_START = 26
CYCLE = 53
REVEAL_START = 1.3
FINALE_FADE = 24
COLORS = {
    "black": 16, "dim": 242, "white": 255, "gold": 222, "coin": 178, "shine": 229,
    "green": 114, "mint": 151, "teal": 115, "blue": 109,
    "h": 167, "H": 210, "s": 223, "w": 255, "v": 250,
    "c": 65, "C": 108, "b": 94, "e": 16, "g": 222,
}
# Cool electric violet, magenta, blue and cyan; gold is reserved for the payoff.
LOGO_STOPS = ((153, 105, 244), (199, 103, 230), (150, 115, 247), (106, 160, 255), (99, 218, 244))
WORDMARK_SHADES = tuple(f"electric_{i}" for i in range(32))
for _i, _name in enumerate(WORDMARK_SHADES):
    _position = _i * (len(LOGO_STOPS) - 1) / (len(WORDMARK_SHADES) - 1)
    _segment = min(len(LOGO_STOPS) - 2, int(_position))
    _fraction = _position - _segment
    COLORS[_name] = tuple(round(a + (b - a) * _fraction)
                          for a, b in zip(LOGO_STOPS[_segment], LOGO_STOPS[_segment + 1]))
SGR = {name: f"5;{color}" if isinstance(color, int) else "2;" + ";".join(map(str, color))
       for name, color in COLORS.items()}
# Stock Omarchy wordmark. Local geometry keeps the laundry attachment points
# stable even if the user replaces their branding file with custom text.
LOGO = (
    "                 ▄▄▄",
    " ▄█████▄    ▄███████████▄    ▄███████   ▄███████   ▄███████   ▄█   █▄    ▄█   █▄",
    "███   ███  ███   ███   ███  ███   ███  ███   ███  ███   ███  ███   ███  ███   ███",
    "███   ███  ███   ███   ███  ███   ███  ███   ███  ███   █▀   ███   ███  ███   ███",
    "███   ███  ███   ███   ███ ▄███▄▄▄███ ▄███▄▄▄██▀  ███       ▄███▄▄▄███▄ ███▄▄▄███",
    "███   ███  ███   ███   ███ ▀███▀▀▀███ ▀███▀▀▀▀    ███      ▀▀███▀▀▀███  ▀▀▀▀▀▀███",
    "███   ███  ███   ███   ███  ███   ███ ██████████  ███   █▄   ███   ███  ▄██   ███",
    "███   ███  ███   ███   ███  ███   ███  ███   ███  ███   ███  ███   ███  ███   ███",
    " ▀█████▀    ▀█   ███   █▀   ███   █▀   ███   ███  ███████▀   ███   █▀    ▀█████▀",
    "                                       ███   █▀",
)
LOGO_WIDTH = max(map(len, LOGO))
PANTS = ("████████", "███▄▄███", "███  ███")
BRIEFS = ("████████", "▀██████▀", "  ▀██▀  ")
KNICKERS = ("████████", "████████", " ▀▀  ▀▀ ")
LAUNDRY = ((14, PANTS, "blue"), (28, BRIEFS, "white"), (61, KNICKERS, "mint"))

# Two vertical sprite pixels per cell; spaces are transparent.
GNOME = (
    "       HH     ",
    "      HHhh    ",
    "     HHhhhh   ",
    "    HHhhhhhh  ",
    "   HHhhhhhhhh ",
    "   hhhhhhhhhh ",
    "    ssessess  ",
    "   wwssssww   ",
    "   wwwsswww   ",
    "  CCwwwwwwCc  ",
    " sCCvwwwwvCcs ",
    " ssCCvwwvCcss ",
    "   CCCvvCcc   ",
    "   eeegeeee   ",
    "   CCCcCccc   ",
    "   CCC  ccc   ",
    "   bbb  bbb   ",
    "  bbbb  bbbb  ",
)

# Five-by-seven lettering, packed into four terminal rows with half blocks.
LETTERING = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "11001", "10101", "10011", "10011", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    " ": ("00000",) * 7,
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
}


def block_letters(text):
    pixels = ["0".join(LETTERING[char][row] for char in text) for row in range(7)]
    pixels.append("0" * len(pixels[0]))
    return tuple("".join({("0", "0"): " ", ("1", "0"): "▀", ("0", "1"): "▄", ("1", "1"): "█"}[pair]
                         for pair in zip(pixels[row], pixels[row + 1]))
                 for row in range(0, 8, 2))


def phase_boxes(canvas, y, active, t, *, single=False):
    """Bright boxed current phase, with quieter upcoming steps."""
    labels = ("1. COLLECT UNDERPANTS", "2. ???", "3. PROFIT!")
    shown = [(active, labels[active])] if single else list(enumerate(labels))
    total = sum(len(label) + 4 for _, label in shown) + 2 * (len(shown) - 1)
    if total > canvas.width:
        shown = [(active, labels[active][:max(0, canvas.width - 4)])]
        total = len(shown[0][1]) + 4
    x = (canvas.width - total) // 2
    for index, label in shown:
        color = ("gold" if active == 2 else WORDMARK_SHADES[10 if active == 0 else 31]) if index == active else "dim"
        inner = len(label) + 2
        canvas.text(x, y, "╔" + "═" * inner + "╗", color)
        canvas.text(x, y + 1, "║ " + label + " ║", color)
        canvas.text(x, y + 2, "╚" + "═" * inner + "╝", color)
        if index == active:
            # A travelling glint traces the top and bottom of the active box.
            glint = int(t * 10) % inner
            canvas.text(x + 1 + glint, y, "═", "white")
            canvas.text(x + inner - glint, y + 2, "═", "white")
        x += inner + 4


def question_mark(canvas, x, y, t, n):
    """A chunky thought curls, bobs and shimmers above each puzzled gnome."""
    age = t * 2.5 + n * 1.8
    for row, line in enumerate(block_letters("?")):
        dx = round(math.sin(age + row * 0.7))
        dy = round(math.sin(age * 0.8))
        color = "white" if int(age * 2) % 4 == row else WORDMARK_SHADES[(n * 9 + int(t * 8) + row * 3) % 32]
        canvas.art(x + dx, y + row + dy, (line,), color)


def reveal_letters(canvas, text, y, elapsed, start, *, narrow=False, drop=5):
    """A staggered sweep assembles falling blocks, followed by a light sweep."""
    art = block_letters(text) if not narrow else (text,)
    x = (canvas.width - len(art[0])) // 2
    for row, line in enumerate(art):
        for col, char in enumerate(line):
            if char == " ":
                continue
            seed = (col * 17 + row * 31) % 23
            age = elapsed - start - col * 0.018 - seed * 0.012
            if age < 0:
                continue
            settled = age >= 0.85
            py = y + row - round(drop * (1 - min(1, age / 0.85)) ** 2)
            shade = WORDMARK_SHADES[min(31, col * 32 // len(line))]
            if not settled or abs(col - ((elapsed * 12) % (len(line) + 30) - 15)) < 2:
                shade = "white"
            if elapsed > FINALE_FADE:
                # Dissolve in columns at the end, ready for a new laundry run.
                if elapsed - FINALE_FADE > seed * 0.08 + col * 0.008:
                    continue
                shade = "dim"
            canvas.text(x + col, py, char if settled else "█", shade)


def gold_coins(canvas, t, oy):
    """Deterministic ballistic fountains; no random state or stored particles."""
    if not REVEAL_START <= t < FINALE_FADE + 2:
        return
    latest = int((min(t, FINALE_FADE - 1) - REVEAL_START) * 10)
    for index in range(max(0, latest - 44), latest + 1):
        age = t - REVEAL_START - index / 10
        if age < 0 or age > 4.4:
            continue
        source = index % 3
        seed = (index * 37) % 101
        direction = -1 if index % 2 else 1
        vx = direction * (9 + seed % 26)
        vy = 15 + seed % 9
        x = round(canvas.width // 2 - 23 + source * 23 + vx * age)
        y = round(oy + 22 - vy * age + 5.5 * age * age)
        face = int(age * 7 + index) % 4
        shade = "shine" if face == 0 else "gold" if face == 2 else "coin"
        coin = ("▄███▄", "▀███▀") if face % 2 == 0 else (" ▐█▌ ", " ▐█▌ ")
        canvas.art(x, y, coin, shade)
        if face % 2 == 0 and 0 <= y < canvas.height and 0 <= x + 2 < canvas.width:
            canvas.cells[y][x + 2] = ("$", "coin" if shade == "shine" else "shine", shade)


def profit_scene(t, width, height):
    canvas = Canvas(width, height)
    stage_height = 29 if height >= 29 else 26
    oy = max(0, (height - stage_height) // 2)
    narrow = width < len(block_letters("BETTER COMPUTERS")[0]) + 4 or height < 26
    first_y, second_y = (oy + 3, oy + 8) if not narrow else (oy + 4, oy + 6)
    tagline_y = oy + (13 if height >= 29 else 12) if not narrow else oy + 9
    headline = ((first_y, "BETTER COMPUTERS", REVEAL_START),
                (second_y, "FOR EVERYONE", 3.8))
    if width >= len(block_letters("BE EARNEST. BE SINCERE.")[0]) + 4 and height >= 29:
        creed = ((oy + 17, "BE EARNEST. BE SINCERE.", 12.5),
                 (oy + 22, "BE BRAVE.", 14.5))
    else:
        positions = (14, 19, 24) if height >= 29 else (13, 17, 21)
        if narrow:
            positions = (11, 13, 15)
        creed = tuple((oy + row, text, 12.5 + n * 1.3)
                      for n, (row, text) in enumerate(zip(positions, ("BE EARNEST.", "BE SINCERE.", "BE BRAVE."))))

    gold_coins(canvas, t, oy)
    # Coin fountains begin with the first assembling headline. Clear only the
    # message areas, leaving the surrounding shower visible throughout.
    for y, text in ((oy, "3. PROFIT!"), (tagline_y, "including the gnomes.")):
        canvas.text((width - len(text)) // 2 - 3, y, " " * (len(text) + 6))
    for y, text, start in headline + creed:
        if (y, text, start) in creed and t < start - 0.2:
            continue
        span = len(text) if narrow else len(block_letters(text)[0])
        for row in range(-2, 2 if narrow else 5):
            canvas.text((width - span) // 2 - 2, y + row, " " * (span + 4))

    if t < REVEAL_START and not narrow:
        ox = (width - LOGO_WIDTH) // 2
        for row, line in enumerate(LOGO):
            for col, char in enumerate(line):
                if char != " " and t < ((col * 13 + row * 7) % 19) / 15:
                    canvas.text(ox + col, oy + row + 1 + round(t * 2), char, "dim")
    for y, text, start in headline:
        reveal_letters(canvas, text, y, t, start, narrow=narrow)
    if 7 <= t < FINALE_FADE + 1:
        tagline = "including the gnomes."
        count = min(len(tagline), int((t - 7) * 12))
        x = (width - len(tagline)) // 2
        canvas.text(x, tagline_y, tagline[:count], "gold")
        if count < len(tagline):
            canvas.text(x + count, tagline_y, "█", "white")
        elif t < 10:
            canvas.text(x - 3, tagline_y, "▀" if int(t * 4) % 2 else "▄", "gold")
            canvas.text(x + len(tagline) + 2, tagline_y, "▄" if int(t * 4) % 2 else "▀", "gold")
    if not narrow and 8.5 <= t < 12.2:
        for n in range(3):
            target = width // 2 - 29 + n * 23
            progress = min(1, (t - 8.5) / 1.8)
            gx = round(-18 - n * 20 + (target + 18 + n * 20) * progress)
            if t >= 11:
                gx += round((t - 11) / 1.2 * (width + 18 - target))
            gy = oy + 14 - round(max(0, math.sin(t * 4 + n)) if progress == 1 else 0)
            gnome(canvas, gx, gy, t, walking=progress < 1 or t >= 11,
                  coat=("c", "blue", "teal")[n])
            _, pants, color = LAUNDRY[n]
            canvas.art(gx + 10, gy + 4, pants, color)
    # The actual bottom line gets the same large lettering as the headline.
    # Gnomes make their exit first so neither the creed nor their sprites overlap.
    for y, text, start in creed:
        reveal_letters(canvas, text, y, t, start, narrow=narrow, drop=2)
    phase_boxes(canvas, max(0, oy - 1), 2, t, single=True)
    return canvas


class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.cells = [[(" ", "white", "black") for _ in range(width)] for _ in range(height)]

    def text(self, x, y, text, color="white"):
        if 0 <= y < self.height:
            for i, char in enumerate(text):
                if 0 <= x + i < self.width:
                    self.cells[y][x + i] = (char, color, "black")

    def center(self, y, text, color="white"):
        self.text((self.width - len(text)) // 2, y, text, color)

    def art(self, x, y, lines, color="white"):
        for row, line in enumerate(lines):
            for col, char in enumerate(line):
                if char != " ":
                    self.text(x + col, y + row, char, color)

    def sprite(self, x, y, pixels, mirror=False, coat="c"):
        rows = [row.ljust(14) for row in pixels]
        if mirror:
            rows = [row[::-1] for row in rows]
        for row in range(0, len(rows), 2):
            for col, (upper, lower) in enumerate(zip(rows[row], rows[row + 1])):
                if upper == lower == " ":
                    continue
                upper = coat if upper == "c" else upper
                lower = coat if lower == "c" else lower
                if upper == lower:
                    cell = ("█", upper, "black")
                elif upper == " ":
                    cell = ("▄", lower, "black")
                else:
                    cell = ("▀", upper, lower if lower != " " else "black")
                if 0 <= y + row // 2 < self.height and 0 <= x + col < self.width:
                    self.cells[y + row // 2][x + col] = cell

    def lines(self, color=False):
        result = []
        for row in self.cells:
            if not color:
                result.append("".join(char for char, _, _ in row))
                continue
            line, previous = "", None
            for char, shade, background in row:
                if (shade, background) != previous:
                    line += f"\033[38;{SGR[shade]};48;{SGR[background]}m"
                    previous = (shade, background)
                line += char
            result.append(line + "\033[0m")
        return result


def gnome(canvas, x, y, t, *, walking=False, reaching=False, mirror=False, coat="c"):
    pixels = list(GNOME)
    if walking:
        if int(t * 7) % 2:
            pixels[-3:] = ("   CCC ccc    ", "    bb bbb    ", "    bb bbbb   ")
        else:
            pixels[-3:] = ("    CCC ccc   ", "   bbb  bb    ", "  bbbb  bb    ")
    if reaching:
        # Arms reach above the hat while the gnome jumps for the waistband.
        pixels[2:6] = [row[:1] + "ss" + row[3:11] + "ss" + row[13:] for row in pixels[2:6]]
        pixels[6:12] = [row[:1] + "CC" + row[3:11] + "cc" + row[13:] for row in pixels[6:12]]
    canvas.sprite(round(x), round(y), pixels, mirror=mirror, coat=coat)


def zen_scene(elapsed, width, height):
    """An endless laundry machine: light, cloth, theft, repeat. No captions."""
    canvas = Canvas(width, height)
    ox, oy = (width - LOGO_WIDTH) // 2, max(0, (height - 26) // 2)
    # Two crossing light waves, moving colour and a restrained cloth-like ripple.
    for row, line in enumerate(LOGO):
        for col, char in enumerate(line):
            if char == " ":
                continue
            wave = math.sin(col * 0.15 - elapsed * 1.8)
            dy = round(0.7 * wave * math.sin(elapsed * 0.7))
            shade = round((0.5 + 0.5 * math.sin(col * 0.045 + row * 0.2 - elapsed * 0.8)) * 31)
            light = abs((col + row * 3 - elapsed * 19) % (LOGO_WIDTH + 25) - 12)
            canvas.text(ox + col, oy + row + 1 + dy, char, "white" if light < 1.5 else WORDMARK_SHADES[shade])

    for n, (px, pants, color) in enumerate(LAUNDRY):
        t = (elapsed + n * 4) % 15
        # Materialize fresh cloth from the waistband down, while other lanes run.
        if t < 7:
            sway = round(math.sin(elapsed * 2 + n))
            canvas.art(ox + px + 2, oy + 10, ("▐  ▌",), WORDMARK_SHADES[31])
            for row, line in enumerate(pants):
                if t >= row * 0.35:
                    forming = t < row * 0.35 + 0.35
                    canvas.art(ox + px + sway, oy + 11 + row,
                               (line,), "white" if forming else color)
        if 2 <= t < 12:
            target = px - 3
            right = n == 1
            edge = width - ox + 3 if right else -ox - 18
            jumping = 6.2 <= t <= 7.8
            if t < 6.2:
                gx = edge + (target - edge) * (t - 2) / 4.2
            elif jumping:
                gx = target
            else:
                gx = target + (edge - target) * (t - 7.8) / 4.2
            jump = 3 * math.sin(math.pi * (t - 6.2) / 1.6) if jumping else 0
            gy = 15 - jump
            gnome(canvas, ox + gx, oy + gy, elapsed, walking=not jumping,
                  reaching=jumping, mirror=right, coat=("c", "blue", "teal")[n])
            if t >= 7:
                carry_x = 3 if jumping else -4 if right else 10
                canvas.art(ox + round(gx) + carry_x, oy + round(gy) + (1 if jumping else 4), pants, color)
    return canvas


def scene(elapsed, width=100, height=36, mode="story"):
    """Pure deterministic terminal frame; all artwork uses single-cell blocks."""
    if mode == "zen":
        return zen_scene(elapsed, width, height)
    canvas = Canvas(width, height)
    clock = elapsed % CYCLE
    if clock >= PROFIT_START:
        return profit_scene(clock - PROFIT_START, width, height)
    # Keep the choreography, with a 21-second heist and a five-second huddle.
    # The payoff keeps its full reading and celebration time.
    t = clock * 27 / HEIST_END if clock < HEIST_END else 27 + (clock - HEIST_END) * 1.6
    labels = ("1. COLLECT UNDERPANTS", "2. ???", "3. PROFIT!")
    if width < LOGO_WIDTH or height < 26:
        # A cropped logo is unreadable: keep the character and joke at small sizes.
        y = max(0, (height - 15) // 2)
        canvas.center(y, "OMARCHY"[:width], WORDMARK_SHADES[10])
        if height >= 15 and width >= 20:
            gnome(canvas, (width - 14) // 2, y + 2, t, walking=True)
        phase_boxes(canvas, max(0, height - 3), 0 if t < 27 else 1, clock, single=True)
        return canvas

    stage_height = 32 if height >= 32 else 29
    ox, oy = (width - LOGO_WIDTH) // 2, max(0, (height - stage_height) // 2)
    # Gentle whole-scene drift only where there is space.
    ox += round(min(2, max(0, (width - LOGO_WIDTH) // 2)) * math.sin(t / 7))
    oy += round(min(1, max(0, (height - stage_height) // 2)) * math.sin(t / 9))

    def art(x, y, lines, color="white"):
        canvas.art(ox + x, oy + y, lines, color)

    def center(y, text, color="white"):
        canvas.text(ox + (LOGO_WIDTH - len(text)) // 2, oy + y, text, color)

    # Interlaced terminal rows slide in from opposite sides and lock into place.
    # A bright horizontal scanner then travels down the electric-colour logo.
    bob = 0
    scanner = (clock * 4) % 16 - 3
    for row, line in enumerate(LOGO):
        for col, char in enumerate(line):
            if char == " ":
                continue
            gradient = (col + row * 2) / (LOGO_WIDTH + 20) + 0.08 * math.sin(clock + row * 0.2)
            color = WORDMARK_SHADES[min(31, max(0, round(gradient * 31)))]
            if abs(row - scanner) < 0.6:
                color = "white"
            elif 0.6 <= scanner - row < 1.6:
                color = WORDMARK_SHADES[31]
            dx, dy = 0, bob
            if t < 3:
                age = t - row * 0.11
                if age < 0:
                    continue
                progress = min(1, age / 1.4)
                dx = round((1 - progress) ** 2 * (LOGO_WIDTH + ox) * (-1 if row % 2 else 1))
                if progress < 1:
                    color = "white" if progress > 0.8 else color
            canvas.text(ox + col + dx, oy + row + 1 + dy, char, color)

    for n, (px, pants, color) in enumerate(LAUNDRY):
        start, pickup = 3 + n * 7, 8 + n * 7
        if 2.7 <= t < pickup:
            # Clothespins actually touch the bottom of the M, A and H.
            art(px + 2, 9 + bob, ("▐  ▌", "▐  ▌"), "gold")
            art(px, 11 + bob, pants, color)
        if start <= t < pickup + 4:
            target = px - 3
            from_right = n == 1
            edge = width - ox + 2 if from_right else -ox - 15
            if t < pickup - 0.8:
                progress = (t - start) / 4.2
                gx = edge + (target - edge) * progress
            elif t <= pickup + 0.8:
                gx = target
            else:
                progress = (t - pickup - 0.8) / 3.2
                gx = target + (edge - target) * progress
            jumping = pickup - 0.8 <= t <= pickup + 0.8
            jump = (3 - bob) * math.sin(math.pi * (t - pickup + 0.8) / 1.6) if jumping else 0
            gy = 14 - jump
            gnome(canvas, ox + gx, oy + gy, t, walking=not jumping,
                  reaching=jumping, mirror=from_right, coat=("c", "blue", "teal")[n])
            if t >= pickup:
                carry_x = 3 if jumping else -4 if from_right else 10
                art(round(gx) + carry_x, round(gy) + (1 if jumping else 4), pants, color)

    if 27 <= t < 35:
        # The conspirators reconvene underneath the unchanged Omarchy logo.
        for n in range(3):
            target = 13 + n * 21
            edge = -ox - 16 - n * 16
            progress = min(1, (t - 27) / 3)
            gx = edge + (target - edge) * progress
            gy = 16 if height >= 32 else 14
            gnome(canvas, ox + gx, oy + gy, t, walking=progress < 1,
                  coat=("c", "blue", "teal")[n])
            if progress == 1:
                question_mark(canvas, ox + target + 5, oy + gy - 5, t, n)
            _, pants, color = LAUNDRY[n]
            art(round(gx) + 10, gy + 4, pants, color)

    phase = 0 if t < 27 else 1
    box_y = min(height - 4, oy + stage_height - 6)
    phase_boxes(canvas, box_y, phase, clock)
    if phase == 0:
        caption = "boxers. briefs. knickers. consider this a heist."
    else:
        caption = "anyone remember step two?"
    center(box_y - oy + 3, caption, "dim")
    return canvas


def animate(args):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Run inside a terminal, or use --frame for a text preview.")
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    start = time.monotonic()
    previous = []
    size_before = None
    stop = Path(args.stop_file) if args.stop_file else None
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?1049h\033[?25l\033[?7l\033[40m\033[2J")
        if not args.preview:
            sys.stdout.write("\033[?1003h\033[?1006h")
        sys.stdout.flush()
        while not (stop and stop.exists()):
            now = time.monotonic()
            if args.duration and now - start >= args.duration:
                break
            size = shutil.get_terminal_size()
            # Cap extreme terminal sizes while preserving the terminal's centering.
            width, height = min(size.columns, 320), min(size.lines, 120)
            lines = scene(now - start + args.offset, width, height, args.mode).lines(True)
            output = []
            if size != size_before:
                output.append("\033[2J")
                previous = []
                size_before = size
            left, top = (size.columns - width) // 2, (size.lines - height) // 2
            for row, line in enumerate(lines):
                if row >= len(previous) or previous[row] != line:
                    output.append(f"\033[{top + row + 1};{left + 1}H" + line)
            if output:
                # Keep a repaint atomic in terminals supporting synchronized
                # output (including stock Foot), avoiding partially drawn rows.
                sys.stdout.write("\033[?2026h" + "".join(output) + "\033[?2026l")
                sys.stdout.flush()
            previous = lines
            if select.select([fd], [], [], max(0, 1 / 12 - (time.monotonic() - now)))[0]:
                data = os.read(fd, 4096)
                # Ignore mouse reports caused by mapping the fullscreen terminal.
                if not data or not data.startswith(b"\033[<") or time.monotonic() - start > 0.8:
                    break
    finally:
        if stop:
            stop.touch()
        sys.stdout.write("\033[?2026l\033[?1003l\033[?1006l\033[0m\033[?7h\033[?25h\033[?1049l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


TRUSTED_BIN_DIRS = ("/usr/bin", "/bin")


def resolve_session_exec(name):
    """Return an allowlisted absolute executable. Never search ambient PATH."""
    if not name or name in (".", "..") or os.sep in name:
        raise RuntimeError(f"Refusing unsafe tool name {name}.")
    for directory in TRUSTED_BIN_DIRS:
        candidate = os.path.join(directory, name)
        try:
            if not os.path.lexists(candidate):
                continue
            real = os.path.realpath(candidate)
            if not os.path.isfile(real) or not os.access(real, os.X_OK):
                continue
        except OSError:
            continue
        if real == directory or real.startswith(directory + os.sep):
            return real
    raise RuntimeError(f"Refusing to proceed without a trusted {name}.")


def run_capped(argv, *, timeout, env=None, max_stdout=PRODUCER_STDOUT_MAX, max_stderr=PRODUCER_STDERR_MAX):
    """Run a local helper, killing it as soon as a stream exceeds its ceiling."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout = bytearray()
    stderr = bytearray()
    streams = {
        proc.stdout: (stdout, max_stdout),
        proc.stderr: (stderr, max_stderr),
    }
    deadline = time.monotonic() + timeout
    oversized = False
    try:
        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            ready, _, _ = select.select(list(streams), [], [], remaining)
            if not ready:
                if proc.poll() is not None:
                    ready, _, _ = select.select(list(streams), [], [], 0)
                    if not ready:
                        break
                continue
            for stream in ready:
                buf, limit = streams[stream]
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    stream.close()
                    del streams[stream]
                    continue
                buf.extend(chunk)
                if len(buf) > limit:
                    oversized = True
                    if proc.poll() is None:
                        proc.kill()
        if proc.poll() is None:
            remaining = deadline - time.monotonic()
            try:
                proc.wait(timeout=max(0.01, remaining))
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
                raise subprocess.TimeoutExpired(argv, timeout)
    except Exception:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=1)
            except Exception:
                pass
        raise
    finally:
        for stream in list(streams):
            try:
                stream.close()
            except OSError:
                pass
    if oversized:
        raise RuntimeError("Refusing oversized command output.")
    return subprocess.CompletedProcess(argv, proc.returncode, bytes(stdout), bytes(stderr))


def hypr(*args, json_output=False):
    result = run_capped([resolve_session_exec("hyprctl"), *args], timeout=3)
    stdout = result.stdout.decode()
    stderr = result.stderr.decode()
    if result.returncode:
        raise RuntimeError(stderr.strip() or stdout.strip())
    return json.loads(stdout) if json_output else stdout


def focus_monitor(name):
    # Current Lua Hyprland, with compatibility for the previous dispatcher.
    try:
        result = hypr("dispatch", f"hl.dsp.focus({{ monitor = {json.dumps(name)} }})")
        if "ok" in result.lower():
            return
    except RuntimeError:
        pass
    hypr("dispatch", "focusmonitor", name)


def terminal_command(terminal, runner):
    if not os.environ.get("OMARCHY_PATH"):
        raise RuntimeError("An Omarchy session is required (OMARCHY_PATH is missing).")
    base = Path(os.environ["OMARCHY_PATH"]) / "default"
    terminal = terminal.lower()
    if "foot" in terminal:
        return ["foot", "--app-id=" + APP_ID, "--fullscreen", "--config=" + str(base / "foot/screensaver.ini"), "-e", *runner]
    if "alacritty" in terminal:
        return ["alacritty", "--class=" + APP_ID, "--config-file", str(base / "alacritty/screensaver.toml"), "-o", "window.startup_mode=\"Fullscreen\"", "-e", *runner]
    if "ghostty" in terminal:
        return ["ghostty", "--class=" + APP_ID, "--config-file=" + str(base / "ghostty/screensaver"), "--fullscreen=true", "--font-size=18", "-e", *runner]
    if "kitty" in terminal:
        return ["kitty", "--class=" + APP_ID, "--start-as=fullscreen", "--override", "font_size=18", "--override", "background=#000000", "--override", "window_padding_width=0", *runner]
    raise RuntimeError("Select Foot, Alacritty, Ghostty, or Kitty as your default terminal.")


def owned_terminal_setup():
    """Linux parent-death signal closes terminals even if QML kills the launcher.

    Construct before fork; the launcher is single-threaded. The parent identity
    check closes the small race between fork and registering PR_SET_PDEATHSIG.
    """
    parent = os.getpid()
    libc = ctypes.CDLL(None, use_errno=True)

    def setup():
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        if libc.prctl(1, int(signal.SIGTERM), 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            os._exit(1)
        if os.getppid() != parent:
            os._exit(0)

    return setup


def session_lock_name():
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "default")
    if not signature or len(signature) > 128 or not all(c.isalnum() or c in "._-" for c in signature):
        raise RuntimeError("Refusing an unsafe Hyprland instance signature.")
    return signature + ".lock"


def _require_private_dir(fd, label):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"Refusing to use {label}: not a directory.")
    if info.st_uid != os.geteuid():
        raise RuntimeError(f"Refusing to use {label}: unexpected owner.")
    if info.st_mode & 0o077:
        raise RuntimeError(f"Refusing to use {label}: group or other access is not allowed.")


def _require_private_lock(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("Refusing to use a non-regular screensaver lock.")
    if info.st_uid != os.geteuid():
        raise RuntimeError("Refusing to use a screensaver lock with an unexpected owner.")
    if info.st_nlink != 1:
        raise RuntimeError("Refusing to use a linked screensaver lock.")
    if info.st_mode & 0o177:
        raise RuntimeError("Refusing to use a screensaver lock that is accessible to others.")
    return info


def _open_lock_fd(private_fd):
    name = session_lock_name()
    try:
        fd = os.open(name, LOCK_CREATE_FLAGS, 0o600, dir_fd=private_fd)
    except FileExistsError:
        try:
            fd = os.open(name, LOCK_REOPEN_FLAGS, dir_fd=private_fd)
        except OSError as error:
            raise RuntimeError("Refusing to open the screensaver lock.") from error
    except OSError as error:
        raise RuntimeError("Refusing to create the screensaver lock.") from error
    try:
        _require_private_lock(fd)
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
    except Exception:
        os.close(fd)
        raise
    return fd


@contextlib.contextmanager
def session_lock():
    """Yield a verified private runtime directory after taking its exclusive lock.

    Returns None if another Underpants instance already holds the lock. Any
    symlink, ownership, type, or link-count problem fails closed.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("Refusing to create a session lock without no-follow directory support.")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise RuntimeError("A graphical login session is required (XDG_RUNTIME_DIR is missing).")
    runtime = runtime.rstrip("/") or runtime
    if not os.path.isabs(runtime) or "\x00" in runtime:
        raise RuntimeError("A graphical login session is required (XDG_RUNTIME_DIR is invalid).")

    runtime_fd = private_fd = lock_fd = None
    try:
        try:
            runtime_fd = os.open(runtime, DIR_OPEN_FLAGS)
        except OSError as error:
            raise RuntimeError("Refusing to use XDG_RUNTIME_DIR: it must be a private directory.") from error
        _require_private_dir(runtime_fd, "XDG_RUNTIME_DIR")
        try:
            os.mkdir(RUNTIME_SUBDIR, 0o700, dir_fd=runtime_fd)
        except FileExistsError:
            pass
        try:
            private_fd = os.open(RUNTIME_SUBDIR, DIR_OPEN_FLAGS, dir_fd=runtime_fd)
        except OSError as error:
            raise RuntimeError("Refusing to use the Underpants runtime directory.") from error
        _require_private_dir(private_fd, "the Underpants runtime directory")
        lock_fd = _open_lock_fd(private_fd)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
            return
        _require_private_lock(lock_fd)
        # Hold the private-dir inode. Use the launcher PID so children inherit a
        # path that still names this process after they exec (O_CLOEXEC + /proc/self).
        yield Path("/proc") / str(os.getpid()) / "fd" / str(private_fd)
    finally:
        for fd in (lock_fd, private_fd, runtime_fd):
            if fd is not None:
                os.close(fd)


def launch(args):
    monitors = hypr("monitors", "-j", json_output=True)
    if any(c.get("class") == APP_ID for c in hypr("clients", "-j", json_output=True)):
        return
    terminal = getattr(args, "terminal", None)
    if not terminal:
        listed = run_capped([resolve_session_exec("xdg-terminal-exec"), "--print-id"], timeout=3)
        if listed.returncode:
            raise RuntimeError((listed.stderr or listed.stdout).decode().strip() or "xdg-terminal-exec failed")
        terminal = listed.stdout.decode().strip()
    original = next((m["name"] for m in monitors if m.get("focused")), None)
    children = []
    with session_lock() as state_dir:
        if state_dir is None:
            return
        # Recheck under the lock: another launch may have mapped its windows
        # between the first compositor query and our lock acquisition.
        if any(c.get("class") == APP_ID for c in hypr("clients", "-j", json_output=True)):
            return
        with tempfile.TemporaryDirectory(prefix="underpants-", dir=str(state_dir)) as session:
            stop = Path(session) / "stop"
            try:
                for monitor in monitors:
                    if stop.exists():
                        break
                    focus_monitor(monitor["name"])
                    runner = [sys.executable, str(Path(__file__).resolve()), "--stop-file", str(stop), "--offset", str(args.offset), "--mode", args.mode]
                    if args.preview:
                        runner.append("--preview")
                    if args.duration:
                        runner += ["--duration", str(args.duration)]
                    children.append(subprocess.Popen(terminal_command(terminal, runner), preexec_fn=owned_terminal_setup()))
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if children[-1].poll() is not None:
                            raise RuntimeError("The screensaver terminal exited during startup.")
                        clients = hypr("clients", "-j", json_output=True)
                        if any(c.get("class") == APP_ID and c.get("monitor") == monitor["id"] for c in clients):
                            break
                        time.sleep(0.05)
                    else:
                        raise RuntimeError("The screensaver terminal did not appear on " + monitor["name"])
                if original:
                    focus_monitor(original)
                while children and not stop.exists() and all(p.poll() is None for p in children):
                    time.sleep(0.5)
                    active = hypr("activewindow", "-j", json_output=True)
                    if active.get("class") != APP_ID:
                        break
            finally:
                stop.touch()
                for child in children:
                    if child.poll() is None:
                        child.terminate()
                for child in children:
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true", help="open the screensaver on every monitor")
    parser.add_argument("--mode", choices=("story", "zen"), default="story", help="story payoff or endless text-free laundry")
    parser.add_argument("--terminal", help="override the default terminal for launch")
    parser.add_argument("--preview", action="store_true", help="watch without mouse-motion dismissal; any key still exits")
    parser.add_argument("--frame", type=float, help="print a plain-text frame at this second and exit")
    parser.add_argument("--width", type=int, default=100)
    parser.add_argument("--height", type=int, default=36)
    parser.add_argument("--offset", type=float, default=0, help="start at this second in the story")
    parser.add_argument("--duration", type=float, default=0, help="automatically exit after this many seconds")
    parser.add_argument("--stop-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("frame", "offset", "duration"):
        value = getattr(args, name)
        if value is not None and (not math.isfinite(value) or value < 0):
            parser.error(f"--{name} must be a finite, non-negative number")
    if args.frame is not None:
        if not (1 <= args.width <= 320 and 1 <= args.height <= 120):
            parser.error("frame size must be within 1..320 columns and 1..120 rows")
        print("\n".join(scene(args.frame, args.width, args.height, args.mode).lines()))
        return

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        launch(args) if args.launch else animate(args)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"Underpants Gnomes: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
