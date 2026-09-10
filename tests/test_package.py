import hashlib
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package", ROOT / "scripts/package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def test_reproducible_archive_with_exact_sources_and_no_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first = package.build(Path(directory) / "a")
            second = package.build(Path(directory) / "b")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            checksum = first.with_suffix(first.suffix + ".sha256").read_text().split()[0]
            self.assertEqual(checksum, hashlib.sha256(first.read_bytes()).hexdigest())
            with tarfile.open(first) as archive:
                members = archive.getmembers()
                self.assertEqual(len(members), len(package.FILES))
                for member in members:
                    self.assertTrue(member.isfile())
                    self.assertEqual(member.mode, 0o644)
                    path = member.name.split("/", 1)[1]
                    self.assertIn(path, package.FILES)
                    self.assertEqual(archive.extractfile(member).read(), (ROOT / path).read_bytes())
                    self.assertNotIn("__pycache__", member.name)
                    self.assertNotIn("submission-draft", member.name)
