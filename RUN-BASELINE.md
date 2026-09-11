# Run the official marketplace Automated Security Baseline

This is the same Node CLI GitHub Actions bots run on
[omacom/omarchy-plugin-marketplace](https://github.com/omacom/omarchy-plugin-marketplace)
after validation writes `validation-metadata.json`.

It is a static exact-commit check, not a security audit. It does not execute
plugin code. Official workflows use Node 24.

There is no marketplace-verify packet in this repository. Use the wrapper
below, or the raw bot command.

## Wrapper (this repo)

```bash
bash scripts/run-marketplace-security-baseline.sh \
  --repo https://github.com/rdoupe-omarchy/omarchy-underpants \
  --sha aab69655c08c9d0e0769be854bd44f58b4c59aac
```

From a plugin checkout (infers `origin` + `HEAD` unless overridden):

```bash
bash scripts/run-marketplace-security-baseline.sh --local .
```

## Exact bot command

```bash
git clone --depth 1 https://github.com/omacom/omarchy-plugin-marketplace.git \
  /tmp/omarchy-plugin-marketplace

# Official writeValidationMetadata fields, plus listedPlugins.entryPoints
# from that commit's root manifest.json. The scanner requires
# listedPlugins[].pluginId and listedPlugins[].manifestPathHint.
cat > /tmp/validation-metadata.json <<'EOF'
{
  "schemaVersion": 1,
  "repoUrl": "https://github.com/rdoupe-omarchy/omarchy-underpants",
  "commitSha": "aab69655c08c9d0e0769be854bd44f58b4c59aac",
  "pluginIds": ["douper.underpants"],
  "listedPlugins": [
    {
      "pluginId": "douper.underpants",
      "manifestPathHint": "manifest.json",
      "entryPoints": { "overlay": "Launcher.qml" }
    }
  ],
  "entryPoints": ["Launcher.qml"]
}
EOF

node /tmp/omarchy-plugin-marketplace/scripts/security-baseline.mjs \
  --metadata=/tmp/validation-metadata.json \
  --json=/tmp/security-baseline.json
```

Stdout is the markdown report bots post. `--json` is the machine-readable
`outcome`, `findings`, `capabilities`, and `verifiedPublicationDisposition`.

Exit `0` means a complete result (`passed`, `review-required`, or
`needs-fixes`). Exit `3` is a scan-limit failure. Exit `2` is an invalid or
unavailable scan.

## What this catch set is

V3 selective policy findings (only these):

- `curl-pipe-shell`
- `cargo-git-unpinned`
- `remote-git-execution-unpinned`
- `sudoers-dangerous-passwordless-command`
- `privileged-process-control-from-shared-temp`

Capabilities (review, not findings): `installer`, `package-manager`,
`privilege`, `remote-build`, `bundled-executable-binary`,
`service-management`, `sudoers-modification`.

The public scanner does **not** detect generic `open("w")` + `flock` TOCTOU,
AGENTS.md prompt injection, or other review-only issues. Those comments are
human/AI maintainer review, not `security-baseline.mjs`.
