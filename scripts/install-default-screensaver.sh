#!/bin/bash
# Write a fixed-path idle launcher. Does not mutate PATH or any shell rc.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=trusted_exec.sh
source "$here/trusted_exec.sh"
python3="$(underpants_resolve python3)"
underpants_run "$python3" "$here/safe_publish.py" install-wrapper --home "$HOME"

wrapper="$HOME/.local/bin/underpants-launch-screensaver"
cat << MSG
Wrote $wrapper

This is a fixed absolute launcher, not a PATH override. Omarchy idle still
runs the stock command by name via bash -lc; do not prepend directories onto
PATH to intercept /usr/bin/omarchy-launch-screensaver.

Point a keybind or user idle hook at the exact path above. Test with:

  $wrapper force

Optional: export UNDERPANTS_MODE=zen for Zen as the idle default.
This script does not edit your shell rc. Undo: remove the launcher file.
MSG
