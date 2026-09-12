# Shared fail-closed tool resolution for the optional installers.
# Search only allowlisted absolute directories. Never search ambient PATH.
# shellcheck shell=bash

UNDERPANTS_DEFAULT_TRUSTED_PATH="/usr/bin:/bin"

underpants_trusted_path() {
  local extra="${UNDERPANTS_TRUSTED_PATH:-}"
  local path="$UNDERPANTS_DEFAULT_TRUSTED_PATH"
  if [[ -n $extra ]]; then
    path="$extra:$path"
  fi
  local dir out=""
  local IFS=':'
  for dir in $path; do
    [[ $dir == /* ]] || continue
    [[ $dir == *..* ]] && continue
    out+="${out:+:}$dir"
  done
  printf '%s\n' "${out:-$UNDERPANTS_DEFAULT_TRUSTED_PATH}"
}

underpants_is_trusted_real() {
  local real="$1" dir
  local IFS=':'
  for dir in $(underpants_trusted_path); do
    if [[ $real == "$dir" || $real == "$dir"/* ]]; then
      return 0
    fi
  done
  return 1
}

underpants_resolve() {
  local name="$1"
  case "$name" in
    ''|.|..|*/*)
      printf 'Refusing unsafe tool name: %s\n' "$name" >&2
      return 1
      ;;
  esac
  local dir cand real
  local IFS=':'
  for dir in $(underpants_trusted_path); do
    cand="$dir/$name"
    if [[ -f $cand && -x $cand ]]; then
      real="$(readlink -f -- "$cand" 2>/dev/null)" || continue
      if underpants_is_trusted_real "$real"; then
        printf '%s\n' "$cand"
        return 0
      fi
    fi
  done
  printf 'Refusing to proceed without a trusted %s (searched %s).\n' "$name" "$(underpants_trusted_path)" >&2
  return 1
}

underpants_run() {
  local session=false
  if [[ ${1:-} == --session ]]; then
    session=true
    shift
  fi
  local env_bin
  env_bin="$(underpants_resolve env)" || return 1
  local -a env_args=(
    "PATH=$(underpants_trusted_path)"
    "HOME=${HOME:-}"
    "LANG=${LANG:-C.UTF-8}"
  )
  local var
  while IFS= read -r var; do
    [[ -n $var ]] || continue
    env_args+=("$var=${!var}")
  done < <(compgen -v UNDERPANTS_ || true)
  if [[ $session == true ]]; then
    local key
    for key in USER LOGNAME XDG_RUNTIME_DIR XDG_SESSION_TYPE XDG_SESSION_ID \
               XDG_CONFIG_HOME WAYLAND_DISPLAY DISPLAY \
               HYPRLAND_INSTANCE_SIGNATURE OMARCHY_PATH DBUS_SESSION_BUS_ADDRESS; do
      if [[ -n ${!key-} ]]; then
        env_args+=("$key=${!key}")
      fi
    done
  fi
  "$env_bin" -i "${env_args[@]}" "$@"
}
