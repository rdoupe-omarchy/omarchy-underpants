# Testing

Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q screensaver.py scripts tests
bash -n install.sh scripts/install-default-screensaver.sh
shellcheck install.sh scripts/install-default-screensaver.sh tests/fixtures/*
omarchy plugin validate .
qmllint -I "$OMARCHY_PATH/shell" Launcher.qml
python3 scripts/package.py
```

The Python suite covers Story/Zen rendering, phase boxes, moving question marks and coins, readable final lettering, dimensions, CLI rejection paths, all four terminal command builders, mocked multi-monitor launch/cleanup, no-follow/exclusive session-lock creation (symlink, FIFO, hardlink and world-accessible runtime rejection), PTY dismissal/restoration, installer consent/backups, no-follow/exclusive installer publish (symlink parents, planted wrapper/plugin names, FIFO and existing-file refusal), QML cancellation/reopening and byte-reproducible packaging.

It also renders every 12-fps frame through one complete Story loop/reset and two Zen theft cycles, including ANSI colour encoding, and verifies Linux parent-death cleanup when the launcher is forcibly killed.

Installer tests use a temporary fixture home and fake shell commands; they never rescan or enable the live desktop. They prefer the real Omarchy manifest validator and fall back to a fixture that only checks the shipped file set and manifest id. The QML test uses offscreen software rendering, a temporary runtime directory, no desktop sockets and a fake Python renderer; it requires Quickshell. Missing optional test tools are reported as skipped, not as verified runtime coverage.

## Private-desktop acceptance

Use a disposable Omarchy session or the SSH-only `agent-desktop`, never the user's active screen. Verify its isolation first. Test both JSON payloads through the actual shell plugin host, Escape dismissal, shell hide, duplicate summon, disable/re-enable, shell restart and removal. Verify only owned screensaver processes disappear. Do not change idle/lock timings to test this plugin.

`tests/acceptance.py` automates the actual-host lifecycle matrix on the dedicated beeserve test desktop. It requires the explicit `UNDERPANTS_GUI_TEST=1` opt-in and refuses to replace an existing plugin or interrupt an existing screensaver. It installs the candidate, restarts only that test shell, runs the checks and removes the test installation with Omarchy's recoverable removal command. Quickshell's component cache means an explicit test-shell restart is needed between candidate revisions. All screenshots and generated logs stay out of the release archive unless deliberately promoted as a clean preview.

The GitHub Actions workflow runs the portable tests on Python 3.11 and 3.14. Its generic Ubuntu runners skip installer/QML tests when Omarchy or Quickshell is unavailable; local Omarchy checks and the private-desktop acceptance run remain required. Configuring CI is not evidence that a remote CI run has happened.

For direct previews in that private session:

```bash
python3 screensaver.py --launch --preview --mode story --duration 60
python3 screensaver.py --launch --preview --mode zen --duration 35
```

Exercise ordinary mouse dismissal without `--preview`, and keyboard dismissal with it. Test window closure and focus loss. Inspect phase 2, the final creed and a full Zen generation/theft cycle. Foot is the reference terminal. Alacritty, Ghostty and Kitty command construction is unit-tested; do not claim their live rendering has passed until each is exercised on an installed system.

## Upstream checks

Omarchy's `test/all` is the core OS CLI/shell suite, not this plugin's test suite. It excludes graphical acceptance. Run it only in an isolated session with user state protected; unrelated failures or compositor-dependent skips must be recorded separately and must not be presented as plugin failures or hidden behind an overall pass.
