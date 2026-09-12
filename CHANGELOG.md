# Changelog

## 2.0.1 — Unreleased

- Document a fixed-path idle launcher (`~/.local/bin/underpants-launch-screensaver`) instead of a login-shell PATH override.
- Optional `scripts/install-default-screensaver.sh` writes that launcher, prints its absolute path, and reports a leftover `omarchy-launch-screensaver` PATH-override wrapper (does not edit shell rc or PATH).
- Resolve installer and wrapper tools from an allowlisted absolute directory list (`/usr/bin:/bin`) with a minimal closed environment; never search ambient PATH for `python3`, `omarchy`, `pgrep`, or `omarchy-toggle-enabled`.
- Create the session lock in a verified private XDG runtime subdirectory with no-follow/exclusive descriptor-safe open, owner/type/link checks, and no symlink truncation.
- Publish optional installer writes through held parent fds: exclusive no-follow temps, staged-payload checks, and atomic rename. Refuse unexpected existing wrapper/plugin names instead of truncating through a symlink.

## 2.0.0 — Unreleased

- Bundle Story and Zen as two modes of one standard Omarchy overlay plugin.
- Story: boxed phase labels, animated block question marks, 21-second thefts and an optimistic large-letter payoff with gold coin fountains.
- Zen: continuously animated electric Omarchy wordmark, regenerating laundry and staggered gnome thefts, without story text.
- Separate optional menu entries and keyboard-only preview dismissal.
- Guard duplicate launches and close-before-start cancellation; clean up owned terminals on startup failure, dismissal, signals and abrupt launcher death.
- Wait for plugin discovery before enabling a fresh local installation; document the shell restart needed to clear cached QML after updates.
- Measure mouse-dismissal startup grace when input arrives, including after a slow terminal repaint.
- Validate numeric CLI inputs and explain missing Omarchy sessions without tracebacks.
- Require consent and retain backups when replacing local plugin copies; activation is opt-in.
- Add reproducible packaging, upstream wordmark attribution and expanded isolated tests.
