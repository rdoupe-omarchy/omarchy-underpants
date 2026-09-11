#!/usr/bin/python3
"""Build a deterministic local release; never commits, uploads or publishes."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "manifest.json", "Launcher.qml", "screensaver.py", "README.md", "LICENSE",
    "install.sh", "menu-entries.json", "CHANGELOG.md", "PUBLISHING.md", "TESTING.md",
    "RUN-BASELINE.md", "scripts/package.py", "scripts/run-marketplace-security-baseline.sh",
    "tests/test_screensaver.py", "tests/test_release.py",
    "tests/test_install.py", "tests/test_qml.py", "tests/test_package.py",
    "tests/test_security_baseline_runner.py",
    "tests/LauncherTest.qml", "tests/fixtures/python3", "tests/fixtures/omarchy",
    "tests/fixtures/omarchy-shell",
    "tests/acceptance.py", ".gitignore",
    "preview.png", "assets/zen.png",
)


def build(destination=None):
    version = json.loads((ROOT / "manifest.json").read_text())["version"]
    name = "omarchy-underpants-" + version
    destination = Path(destination) if destination else ROOT / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / (name + ".tar.gz")
    with archive.open("wb") as output, gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as package:
            for path in sorted(FILES):
                source = ROOT / path
                if source.is_symlink():
                    raise ValueError("Refusing release symlink: " + path)
                data = source.read_bytes()
                info = tarfile.TarInfo(name + "/" + path)
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                package.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(digest + "  " + archive.name + "\n")
    return archive


if __name__ == "__main__":
    print(build())
