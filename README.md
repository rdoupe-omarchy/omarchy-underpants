# Underpants Gnomes — Story & Zen

Two screensavers in one standard Omarchy plugin, `douper.underpants`:

- **Story** — a 53-second three-phase heist with boxed, illuminated phase labels, animated block question marks, and an optimistic gold-coin payoff.
- **Zen** — a continuously animated electric Omarchy logo that grows fresh underwear for gnomes to steal. Three staggered 15-second laundry cycles, crossing light sweeps, colour waves and a gentle logo ripple. No captions, phase labels, creed, coins, or story reset.

Both modes share the same renderer and launch lifecycle; no duplicate plugin installations are needed. The default remains Story for existing launchers.

![Story: three puzzled block gnomes under the Omarchy logo, with the second phase highlighted](preview.png)

![Zen: the animated Omarchy logo grows underwear for the gnomes to steal](assets/zen.png)

## Story

A silent block-text terminal screensaver for Omarchy, inspired by [DHH's underpants-gnome post](https://x.com/dhh/status/2097915338956427515). Underpants hang directly from the stock Omarchy wordmark. Solid, red-hatted gnomes sneak in, jump to steal them, and carry them away. The thefts take 21 seconds, followed by a five-second huddle: “anyone remember step two?”

The wordmark's alternating rows slide in from opposite sides and lock into place, then a bright horizontal scanline sweeps down the lettering. The opening owns the theft: “boxers. briefs. knickers. consider this a heist.” The copy takes its earnest, optimistic tone from [DHH's September 10 creed](https://x.com/dhh/status/2097919711170203998). The heist is the joke; better computers for everyone, including the gnomes, is the payoff.

At 26 seconds, the logo crumbles and large block letters assemble into **BETTER COMPUTERS / FOR EVERYONE**. Gold coins start spraying as the first headline begins assembling, leaving clear space for the lettering. Then **including the gnomes.** types in gold. After celebrating, the gnomes leave room for **BE EARNEST. BE SINCERE. BE BRAVE.** to assemble in the same large font beneath the headline. The message holds with a travelling highlight before dissolving into the next loop.

Black background, electric violet, magenta, blue and cyan lettering, and coloured sprites made from `█`, `▀`, and `▄`. The logo and payoff lettering use a 32-step true-colour gradient, with gold reserved for the coins and punchline. Each terminal cell holds two vertical sprite pixels using foreground/background colours. A 53-second loop at 12 fps, drawing only changed terminal rows with synchronized output. No images, videos, network calls, sound, or additional Python packages. The animation uses its own terminal renderer; it does not run inside TTE/ttfx.

This is a standard Omarchy shell plugin (`douper.underpants`, kind `overlay`). It uses the default terminal's stock screensaver configuration and the `org.omarchy.screensaver` window class for Omarchy's idle tracking. Supports Foot, Alacritty, Ghostty, and Kitty. Any key, mouse movement, a closed window, or loss of screensaver focus dismisses the session across all monitors. Only terminals created by this plugin are stopped. Both modes use the same session lock, so they cannot stack screensaver windows.

## Install locally

```bash
bash install.sh
```

Requires Omarchy Quattro with its shell plugin API (tested with 4.0.3-1), Python 3.11 or later, Hyprland/`hyprctl`, `xdg-terminal-exec`, and one of the supported terminals. No root access, network access at runtime, background service, native build, or extra Python dependencies are needed. Foot is live-tested; Alacritty, Ghostty and Kitty launch arguments are tested but their live rendering remains unverified.

The installer validates and copies the plugin. Add `--enable` to explicitly rescan and enable it. Replacing an existing local copy requires `--force` and creates a backup first; Git-managed and symlinked copies are not overwritten. Omarchy discovers plugins under `~/.config/omarchy/plugins/`, so the installer intentionally follows that path even if `XDG_CONFIG_HOME` differs. Installing into a watched plugin directory may reload shell code; choose a convenient time. This preparation checkout is separate from the installed copy.

```bash
bash install.sh --enable          # new local installation and explicit activation
bash install.sh --force --enable  # back up and replace an existing local copy
```

Neither installation nor activation edits your menu or idle/lock settings. The plugin is a screensaver, not a security lock. Like all Omarchy plugins it runs unsandboxed with your user permissions; review the source before enabling it. Its only runtime writes are session lock/stop files in a private subdirectory of your runtime directory. It starts its own terminal processes and requests monitor focus while mapping them; dismissal stops only those processes.

After replacing QML in an already loaded copy, restart the shell at a convenient time with `omarchy restart shell`: current Quickshell versions may cache the old component at the same path despite a plugin rescan. The installer does not restart your desktop automatically.

Launch either screensaver through the shell:

```bash
omarchy-shell shell summon douper.underpants '{"mode":"story"}'
omarchy-shell shell summon douper.underpants '{"mode":"zen"}'
```

For two separate menu entries, merge the entries from `menu-entries.json` into your existing `~/.config/omarchy/extensions/omarchy-menu.jsonc` object. Do not replace the file: it may contain other custom entries. The actions are:

```jsonc
{
"system.underpants": {"label":"Underpants Gnomes — Story","action":"omarchy-shell shell summon douper.underpants '{\"mode\":\"story\"}'"},
"system.underpants-zen": {"label":"Underpants Gnomes — Zen","action":"omarchy-shell shell summon douper.underpants '{\"mode\":\"zen\"}'"}
}
```

Enabling the plugin makes Story and Zen available on demand (menu / `omarchy-shell shell summon`). It does **not** by itself replace Omarchy’s stock idle screensaver or change lock timings. To wire Underpants as what idle launches, see [Use as the default idle screensaver](#use-as-the-default-idle-screensaver) below — a community PATH override, not a first-class Omarchy plugin API.

## Use as the default idle screensaver

Omarchy’s idle service runs `bash -lc` → `omarchy-launch-screensaver`. The stock launcher opens one terminal per monitor with `-e omarchy-screensaver` (ttfx). There is **no** official selectable idle-screensaver plugin API; the supported community approach is to put a wrapper named `omarchy-launch-screensaver` earlier on `PATH` than `/usr/bin/omarchy-launch-screensaver`.

**Important:** Omarchy’s `env-bootstrap` **appends** `~/.local/bin` at the end of `PATH`. A wrapper there does **not** beat the stock binary unless you **prepend** `~/.local/bin` for login shells (idle uses `bash -lc`).

1. Install and enable the plugin first (`bash install.sh --enable`, or `omarchy plugin add … --enable`).
2. Create `~/.local/bin/omarchy-launch-screensaver` (or run the optional helper in step 2b):

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/omarchy-launch-screensaver << 'EOF'
#!/bin/bash
# Community PATH override: launch Underpants Gnomes instead of stock ttfx.
# Matches stock early-exit behaviour; does not change lock timings.

pgrep -f '[o]rg.omarchy.screensaver' >/dev/null && exit 0

if omarchy-toggle-enabled screensaver-off && [[ ${1:-} != "force" ]]; then
  exit 1
fi

exec python3 "$HOME/.config/omarchy/plugins/douper.underpants/screensaver.py" \
  --launch --mode "${UNDERPANTS_MODE:-story}"
EOF
chmod +x ~/.local/bin/omarchy-launch-screensaver
```

2b. Optional helper (writes the same wrapper; does **not** edit your shell rc):

```bash
bash scripts/install-default-screensaver.sh
```

3. Prepend `~/.local/bin` for login shells so idle’s `bash -lc` sees the wrapper first. After Omarchy sources its env (e.g. near the end of `~/.bashrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

4. Re-login or restart the shell session so `bash -lc` picks up the new `PATH`.
5. Test:

```bash
omarchy-launch-screensaver force
# and/or System → Screensaver; also wait idle.screensaver seconds with idle enabled
```

Optional: default to Zen with `export UNDERPANTS_MODE=zen` in the same rc (or set it only for the wrapper environment).

**Undo:** remove `~/.local/bin/omarchy-launch-screensaver`; remove the `PATH` prepend if you added it only for this. Stock ttfx returns. This override does not change lock timings.

## Preview and checks

```bash
python3 screensaver.py                 # animate in the current terminal
python3 screensaver.py --frame 9        # print one plain-text frame
python3 screensaver.py --launch         # fullscreen on all monitors
python3 screensaver.py --launch --preview # keyboard-only dismissal for watching
python3 screensaver.py --launch --preview --mode zen
python3 -m unittest discover -s tests
```

For private GUI testing, sync the project with `agent-desktop sync` before launching its remote path with `agent-desktop run`. The optional `--duration 60` exits automatically; `--offset 26` jumps to the payoff reveal.

## Distribution

Version 2.0.1 documents wiring Underpants as the default idle screensaver via a PATH override. Version 2.0.0 bundled both modes under the same MIT-licensed manifest. The directory is ready to be the root of an Omarchy plugin repository; after publishing it, users can install its Git URL with `omarchy plugin add https://github.com/rdoupe-omarchy/omarchy-underpants --enable`. Standard Git installation needs no custom install hook. No public repository is assumed or created by the local installer.

To build a local release archive from this directory:

```bash
python3 scripts/package.py
```

Unpack into a new directory and run `bash install.sh`. To remove the plugin, run `omarchy plugin remove douper.underpants` and remove only its two optional menu entries.

See [TESTING.md](TESTING.md) for verification, [PUBLISHING.md](PUBLISHING.md) for the approval checklist, and [CHANGELOG.md](CHANGELOG.md) for the candidate release notes. The stock Omarchy wordmark is credited to David Heinemeier Hansson in [LICENSE](LICENSE); sprites and renderer additions are by douper. This is an independent community joke, not an official Omarchy product or endorsement.
