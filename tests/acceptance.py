#!/usr/bin/python3
"""Destructive-to-test-state lifecycle checks: disposable remote desktop ONLY."""
import json
import os
import re
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
ID = "douper.underpants"
APP = "org.omarchy.screensaver"


def run(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=20)
    except subprocess.CalledProcessError as error:
        print(error.output, flush=True)
        raise


def windows():
    return [c for c in json.loads(run("hyprctl", "clients", "-j")) if c.get("class") == APP]


def closed():
    script = str(Path.home() / ".config/omarchy/plugins" / ID / "screensaver.py")
    launcher = subprocess.run(["pgrep", "-f", "^/usr/bin/python3 " + re.escape(script) + " --launch"], capture_output=True)
    return not windows() and launcher.returncode == 1


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    print("TIMEOUT windows:", json.dumps(windows()), flush=True)
    result = subprocess.run(["pgrep", "-af", "screensaver.py"], capture_output=True, text=True)
    print(result.stdout, flush=True)
    raise AssertionError("Timed out waiting for screensaver lifecycle")


def open_mode(mode):
    run("omarchy-shell", "shell", "summon", ID, json.dumps({"mode": mode}))
    wait_for(windows)
    time.sleep(1)


def main():
    if os.uname().nodename != "beeserve" or os.environ.get("UNDERPANTS_GUI_TEST") != "1":
        raise SystemExit("Run only via agent-desktop on beeserve with UNDERPANTS_GUI_TEST=1")
    installed = json.loads(run("omarchy", "plugin", "list", "--json"))
    if any(p["id"] == ID for p in installed) or windows():
        raise SystemExit("Refusing to disturb an existing plugin/screensaver session")
    try:
        run("bash", str(ROOT / "install.sh"), "--enable")
        # Quickshell caches components at a URL across plugin rescans. A fresh
        # test shell ensures this run exercises the candidate, not an old QML copy.
        run("omarchy", "restart", "shell")
        wait_for(lambda: ID in run("omarchy", "plugin", "list", "--json"))
        for mode in ("story", "zen"):
            open_mode(mode)
            before = [c["address"] for c in windows()]
            run("omarchy-shell", "shell", "summon", ID, json.dumps({"mode": mode}))
            time.sleep(0.5)
            assert before == [c["address"] for c in windows()], "Duplicate windows"
            # Match agent-desktop's keyboard setup delay; a newly created
            # virtual keyboard may otherwise send before keymap/focus delivery.
            run("wtype", "-s", "150", "-k", "Escape")
            wait_for(closed)
            print("PASS", mode, "host launch, duplicate summon, Escape", flush=True)
            open_mode(mode)
            run("omarchy-shell", "shell", "hide", ID)
            wait_for(closed)
            print("PASS", mode, "reopen and shell hide", flush=True)
        open_mode("zen")
        run("omarchy", "plugin", "disable", ID)
        wait_for(closed)
        run("omarchy", "plugin", "enable", ID)
        open_mode("story")
        run("omarchy-shell", "shell", "hide", ID)
        wait_for(closed)
        print("PASS disable/re-enable", flush=True)
        run("omarchy", "restart", "shell")
        wait_for(lambda: ID in run("omarchy", "plugin", "list", "--json"))
        open_mode("zen")
        run("omarchy-shell", "shell", "hide", ID)
        wait_for(closed)
        print("PASS shell restart and reopen", flush=True)
    finally:
        run("omarchy-shell", "shell", "hide", ID)
        run("omarchy", "plugin", "remove", ID, "--yes")
        wait_for(lambda: ID not in run("omarchy", "plugin", "list", "--json"))
    assert not windows()
    print("PASS removal and owned-window cleanup", flush=True)


if __name__ == "__main__":
    main()
