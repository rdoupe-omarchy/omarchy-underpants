#!/bin/bash
# Local installation; no root, idle changes, or overwriting unrelated menus.
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/trusted_exec.sh
source "$source_dir/scripts/trusted_exec.sh"
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
python3="$(underpants_resolve python3)"
omarchy="$(underpants_resolve omarchy)"
underpants_run "$omarchy" plugin validate "$source_dir"
if [[ $source_dir != "$target" ]]; then
  publish=("$python3" "$source_dir/scripts/safe_publish.py" install-plugin --source "$source_dir" --home "$HOME" --validator "$omarchy" plugin validate)
  if [[ $force == "true" ]]; then
    publish+=(--force)
  fi
  underpants_run "${publish[@]}"
fi
underpants_run "$omarchy" plugin validate "$target"
if [[ $enable == "true" ]]; then
  omarchy_shell="$(underpants_resolve omarchy-shell)"
  jq="$(underpants_resolve jq)"
  underpants_run --session "$omarchy_shell" shell rescanPlugins
  discovered=false
  for (( attempt = 0; attempt < 40; attempt++ )); do
    if underpants_run --session "$omarchy" plugin list --json | underpants_run "$jq" -e 'any(.[]; .id == "douper.underpants")' >/dev/null; then
      discovered=true
      break
    fi
    sleep 0.05
  done
  if [[ $discovered != "true" ]]; then
    printf '%s\n' 'Files installed, but shell discovery timed out. Rescan and enable when the shell is ready.' >&2
    exit 1
  fi
  underpants_run --session "$omarchy" plugin enable douper.underpants
fi
printf '%s\n' 'Installed Story & Zen. Activate with: omarchy-shell shell rescanPlugins && omarchy plugin enable douper.underpants' 'Launch commands and the optional two-entry menu snippet are in README.md.'
