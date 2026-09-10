#!/bin/bash
# Write a PATH-override wrapper so Omarchy idle launches Underpants Gnomes.
# Does NOT edit ~/.bashrc or any shell rc — print the PATH reminder only.
set -euo pipefail

bin_dir="${HOME}/.local/bin"
wrapper="${bin_dir}/omarchy-launch-screensaver"
plugin_py="${HOME}/.config/omarchy/plugins/douper.underpants/screensaver.py"

if [[ ! -f "$plugin_py" ]]; then
  echo "Plugin not found at: $plugin_py" >&2
  echo "Install and enable douper.underpants first (bash install.sh --enable)." >&2
  exit 1
fi

mkdir -p "$bin_dir"

cat > "$wrapper" << 'WRAP'
#!/bin/bash
# Community PATH override: launch Underpants Gnomes instead of stock ttfx.
# Matches stock early-exit behaviour; does not change lock timings.

pgrep -f '[o]rg.omarchy.screensaver' >/dev/null && exit 0

if omarchy-toggle-enabled screensaver-off && [[ ${1:-} != "force" ]]; then
  exit 1
fi

exec python3 "$HOME/.config/omarchy/plugins/douper.underpants/screensaver.py" \
  --launch --mode "${UNDERPANTS_MODE:-story}"
WRAP

chmod +x "$wrapper"

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
