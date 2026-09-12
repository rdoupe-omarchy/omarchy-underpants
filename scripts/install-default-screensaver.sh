#!/bin/bash
# Write a fixed-path idle launcher. Does not mutate PATH or any shell rc.
set -euo pipefail

_self="${BASH_SOURCE[0]}"
if [[ $_self == */* ]]; then
  here="$(cd -- "${_self%/*}" && pwd)"
else
  here="$(pwd)"
fi
# shellcheck source=trusted_exec.sh
source "$here/trusted_exec.sh"
trusted_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --trusted-path)
      if [[ $# -lt 2 ]]; then
        printf 'Missing directory for --trusted-path\n' >&2
        exit 2
      fi
      underpants_add_trusted_dir "$2" || exit 2
      trusted_args+=(--trusted-path "$2")
      shift 2
      ;;
    --trusted-path=*)
      underpants_add_trusted_dir "${1#--trusted-path=}" || exit 2
      trusted_args+=(--trusted-path "${1#--trusted-path=}")
      shift
      ;;
    --help|-h)
      printf '%s\n' 'Usage: bash scripts/install-default-screensaver.sh'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done
python3="$(underpants_resolve python3)"
underpants_run "$python3" "$here/safe_publish.py" install-wrapper --home "$HOME" "${trusted_args[@]}"

wrapper="$HOME/.local/bin/underpants-launch-screensaver"
legacy="$HOME/.local/bin/omarchy-launch-screensaver"
printf '%s\n' \
  "Wrote $wrapper" \
  "" \
  "This is a fixed absolute launcher, not a PATH override. Omarchy idle still" \
  "runs the stock command by name via bash -lc; do not add directories onto" \
  "PATH to intercept /usr/bin/omarchy-launch-screensaver." \
  "" \
  "Point a keybind or user idle hook at the exact path above. Test with:" \
  "" \
  "  $wrapper force" \
  "" \
  "Optional: UNDERPANTS_MODE=zen for Zen as the idle default." \
  "This script does not edit your shell rc. Undo: remove the launcher file."
if [[ -e $legacy || -L $legacy ]]; then
  printf '%s\n' \
    "" \
    "Legacy PATH-override wrapper still present: $legacy" \
    "Remove that file and any login-shell PATH override that selected it, or idle can still execute it by command name."
fi
