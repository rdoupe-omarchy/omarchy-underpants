# Changelog

## 2.0.1 — Unreleased

- Document wiring Underpants as the default Omarchy idle screensaver via a `~/.local/bin` PATH override (prepend required; Omarchy appends that dir last).
- Optional `scripts/install-default-screensaver.sh` writes the wrapper and prints the PATH reminder (does not edit shell rc).
- Create the session lock in a verified private XDG runtime subdirectory with no-follow/exclusive descriptor-safe open, owner/type/link checks, and no symlink truncation.

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
