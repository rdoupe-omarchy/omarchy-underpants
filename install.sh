#!/bin/bash
# Local installation; no root, idle changes, or overwriting unrelated menus.
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Match the shell registry's actual discovery location (not XDG_CONFIG_HOME).
target="$HOME/.config/omarchy/plugins/douper.underpants"
force=false
enable=false
for arg in "$@"; do
  case "$arg" in
    --force) force=true ;;
    --enable) enable=true ;;
    --help|-h)
      printf '%s\n' 'Usage: bash install.sh [--force] [--enable]' 'Existing local copies require --force and are backed up. Activation is opt-in.'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
omarchy plugin validate "$source_dir"
if [[ -L $target || -e $target/.git ]]; then
  printf '%s\n' 'Refusing to overwrite a symlink or Git-managed plugin; update that checkout separately.' >&2
  exit 1
fi
if [[ $source_dir != "$target" ]]; then
  if [[ -e $target ]]; then
    if [[ $force != "true" ]]; then
      printf '%s\n' 'A local plugin already exists. Use --force to back it up and replace it.' >&2
      exit 1
    fi
    omarchy plugin validate "$target"
    backup=$(mktemp -d "$HOME/.config/omarchy/underpants-backup.XXXXXXXX")
    cp -a -- "$target" "$backup/plugin"
    printf 'Saved previous plugin to %s/plugin\n' "$backup"
  fi
  mkdir -p -- "$target"
  install -m644 "$source_dir"/{manifest.json,Launcher.qml,screensaver.py,README.md,LICENSE,menu-entries.json} "$target/"
fi
omarchy plugin validate "$target"
if [[ $enable == "true" ]]; then
  omarchy-shell shell rescanPlugins
  discovered=false
  for (( attempt = 0; attempt < 40; attempt++ )); do
    if omarchy plugin list --json | jq -e 'any(.[]; .id == "douper.underpants")' >/dev/null; then
      discovered=true
      break
    fi
    sleep 0.05
  done
  if [[ $discovered != "true" ]]; then
    printf '%s\n' 'Files installed, but shell discovery timed out. Rescan and enable when the shell is ready.' >&2
    exit 1
  fi
  omarchy plugin enable douper.underpants
fi
printf '%s\n' 'Installed Story & Zen. Activate with: omarchy-shell shell rescanPlugins && omarchy plugin enable douper.underpants' 'Launch commands and the optional two-entry menu snippet are in README.md.'
