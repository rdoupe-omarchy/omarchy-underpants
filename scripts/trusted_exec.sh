# Shared fail-closed tool resolution for the optional installers.
# Search only allowlisted absolute directories. Never search ambient PATH.
# shellcheck shell=bash

UNDERPANTS_DEFAULT_TRUSTED_PATH="/usr/bin:/bin"
UNDERPANTS_EXTRA_TRUSTED_DIRS=()

underpants_add_trusted_dir() {
  local dir="$1"
  if [[ $dir != /* || $dir == *..* ]]; then
    printf 'Refusing untrusted directory: %s\n' "$dir" >&2
    return 1
  fi
  UNDERPANTS_EXTRA_TRUSTED_DIRS+=("$dir")
}

underpants_trusted_path() {
  local path="$UNDERPANTS_DEFAULT_TRUSTED_PATH"
  local dir extra="" out=""
  for dir in "${UNDERPANTS_EXTRA_TRUSTED_DIRS[@]}"; do
    [[ $dir == /* ]] || continue
    [[ $dir == *..* ]] && continue
    extra+="${extra:+:}$dir"
  done
  if [[ -n $extra ]]; then
    path="$extra:$path"
  fi
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

underpants_realpath() {
  local path="$1" rl
  for rl in /usr/bin/readlink /bin/readlink; do
    if [[ -f $rl && -x $rl ]]; then
      "$rl" -f -- "$path" 2>/dev/null
      return $?
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
    if [[ -L $cand || -f $cand ]]; then
      real="$(underpants_realpath "$cand")" || continue
      if [[ -f $real && -x $real ]] && underpants_is_trusted_real "$real"; then
        printf '%s\n' "$real"
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
    "PATH=$UNDERPANTS_DEFAULT_TRUSTED_PATH"
    "HOME=${HOME:-}"
    "LANG=${LANG:-C.UTF-8}"
  )
  local var
  while IFS= read -r var; do
    [[ -n $var ]] || continue
    [[ $var == UNDERPANTS_TRUSTED_PATH ]] && continue
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
