"""Local marketplace baseline runner: metadata matches the bot schema."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run-marketplace-security-baseline.sh"


class SecurityBaselineRunnerTests(unittest.TestCase):
    def test_help_exits_cleanly(self):
        result = subprocess.run(["bash", str(RUNNER), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--metadata-only", result.stdout)

    def test_metadata_only_matches_official_schema_and_root_manifest(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        sha = "aab69655c08c9d0e0769be854bd44f58b4c59aac"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "bash", str(RUNNER),
                    "--local", str(ROOT),
                    "--repo", "https://github.com/rdoupe-omarchy/omarchy-underpants",
                    "--sha", sha,
                    "--out", directory,
                    "--metadata-only",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            path = Path(result.stdout.strip())
            metadata = json.loads(path.read_text())
        self.assertEqual(metadata["schemaVersion"], 1)
        self.assertEqual(metadata["repoUrl"], "https://github.com/rdoupe-omarchy/omarchy-underpants")
        self.assertEqual(metadata["commitSha"], sha)
        self.assertEqual(metadata["pluginIds"], [manifest["id"]])
        self.assertEqual(metadata["listedPlugins"], [{
            "pluginId": manifest["id"],
            "manifestPathHint": "manifest.json",
            "entryPoints": manifest["entryPoints"],
        }])
        self.assertEqual(metadata["entryPoints"], sorted(manifest["entryPoints"].values()))
