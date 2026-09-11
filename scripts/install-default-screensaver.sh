#!/bin/bash
# Write a PATH-override wrapper so Omarchy idle launches Underpants Gnomes.
# Does NOT edit ~/.bashrc or any shell rc — print the PATH reminder only.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$here/safe_publish.py" install-wrapper --home "$HOME"

cat << 'MSG'
Wrote ~/.local/bin/omarchy-launch-screensaver

Omarchy appends ~/.local/bin at the END of PATH by default, so the wrapper will
not beat /usr/bin/omarchy-launch-screensaver until you PREPEND it for login
shells (idle runs bash -lc). Add this after Omarchy sources its env, e.g. near
the end of ~/.bashrc:

  export PATH="$HOME/.local/bin:$PATH"

Then re-login or restart the shell session. Test with:

  omarchy-launch-screensaver force

Optional: export UNDERPANTS_MODE=zen for Zen as the idle default.
This script does not edit your shell rc. Undo: remove the wrapper (and the PATH
prepend if you added it only for this).
MSG
