# Publishing checklist

Status: **unpublished release candidate**. Do not create a repository, push, tag, publish a release, or submit a marketplace issue without the owner's separate approval.

## Rules checked

Reviewed on 2026-09-10:

- [Omarchy plugin development guide](https://plugins.omarchy.org/develop.html): manifest validation, QML lint, lifecycle checks and disclosure of dependencies.
- [Publishing guide](https://plugins.omarchy.org/publish.html): public repository with one root manifest, README, license and safe install/removal.
- [CLI and AI-assisted submission rules](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md): exact form headings, allowed category/tags, owner confirmation and explicit approval before submission.
- [Marketplace security baseline](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SECURITY.md): exact-commit static analysis; an installer is a review capability, not automatic verification or a security audit.
- [Upstream Omarchy contribution conventions](https://github.com/omacom/omarchy/blob/dev/AGENTS.md): Bash shebang/style, focused testing and visual verification. This is a standalone community plugin, not a proposed modification to Omarchy core.

The local Claude Omarchy skill points to the same installed Omarchy skill used by Codex. The local source checkout also contains `manual/32-shell-plugins.md`, `agents/skills/shell-dev.md`, and `docs/testing.md`. No separate screensaver-publishing skill was found.

## Package identity

- One repository, one permanent ID: `douper.underpants`.
- Version: `2.0.1`; keep unpublished changes under this release candidate until release approval.
- Two user-facing modes: Story and Zen; both use the overlay's `mode` JSON payload.
- Suggested category: `Appearance`.
- Suggested tags: `hyprland, quickshell`.
- The ID was absent from the marketplace registry, including retired IDs, when checked. Recheck immediately before submission.
- No mandatory custom install/build step: a standard Git plugin install can launch both modes. Menu customization is optional.

## Before publication

- [ ] Owner chooses/confirms the public GitHub repository URL and permanent ID.
- [ ] Owner confirms ownership/permission for the original sprites, code and preview assets; the stock wordmark is attributed in LICENSE. This project does not claim affiliation with or endorsement by Omarchy or DHH.
- [ ] Run every check in TESTING.md; review any skipped or environment-limited checks explicitly.
- [ ] Review all prospective repository files for private paths, stale previews, generated logs and credentials. The allowlisted release archive omits local screenshots and draft submissions.
- [x] Capture and inspect clean current previews: root `preview.png` for Story and `assets/zen.png` for Zen. Other development screenshots remain excluded.
- [ ] Select the repository URL, then document its exact standard `omarchy plugin add <url> --enable` command in README.
- [ ] Owner approves the local repository contents, initial commit and release tag before any Git operations that publish them.
- [ ] After publication, verify the public repository and exact commit through the marketplace's validation and security-baseline workflow. These checks cannot be claimed for an unpublished directory. Replay the same bot CLI locally with [RUN-BASELINE.md](RUN-BASELINE.md).
- [ ] Show the completed marketplace title/body to the owner. Obtain confirmation of all five checklist statements and explicit issue-submission approval.

Use the exact submission headings from SUBMISSION.md. Leave unconfirmed checklist statements unchecked in a local draft. Never claim a public repository exists before it does. Listing approval is not a security review.

## Local release build

```bash
python3 scripts/package.py
cd dist
sha256sum -c omarchy-underpants-2.0.1.tar.gz.sha256
```

The archive has a single top-level directory, a fixed file allowlist, normalized modes/timestamps, and a SHA-256 checksum. Repeated builds from identical sources produce identical bytes. No network or publishing operation is performed.
