#!/usr/bin/python3
"""Descriptor-safe create/publish helpers for the optional installers.

Pathnames are walked one component at a time with O_NOFOLLOW. Payloads are
written to randomized exclusive temps relative to a held parent fd, read back,
then published with renameat2(RENAME_NOREPLACE) or (for consented --force
overlay) renameat onto a verified regular file. Existing unexpected names are
never opened for truncation.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import os
from pathlib import Path
import secrets
import shlex
import stat
import subprocess
import sys

PLUGIN_ID = "douper.underpants"
PLUGIN_FILES = (
    "manifest.json", "Launcher.qml", "screensaver.py", "README.md", "LICENSE", "menu-entries.json",
)
WRAPPER_NAME = "underpants-launch-screensaver"
WRAPPER_REL = Path(".local") / "bin" / WRAPPER_NAME
PLUGIN_REL = Path(".config") / "omarchy" / "plugins" / PLUGIN_ID
PLUGIN_PY_REL = PLUGIN_REL / "screensaver.py"
BACKUP_PREFIX = "underpants-backup."
TEMP_PREFIX = ".underpants-tmp-"
DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_CREATE_FLAGS = (
    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
)
FILE_PROBE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
RENAME_NOREPLACE = 1
DEFAULT_TRUSTED_PATH = "/usr/bin:/bin"
WRAPPER_TOOLS = ("pgrep", "omarchy-toggle-enabled", "python3", "env")
SESSION_ENV_KEYS = (
    "USER", "LOGNAME", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_SESSION_ID",
    "XDG_CONFIG_HOME", "WAYLAND_DISPLAY", "DISPLAY",
    "HYPRLAND_INSTANCE_SIGNATURE", "OMARCHY_PATH", "DBUS_SESSION_BUS_ADDRESS",
)


class PublishError(RuntimeError):
    """Fail-closed installer error with an exit status."""

    def __init__(self, message, status=1):
        super().__init__(message)
        self.status = status


def trusted_path_dirs():
    extra = os.environ.get("UNDERPANTS_TRUSTED_PATH", "")
    raw = f"{extra}{os.pathsep}{DEFAULT_TRUSTED_PATH}" if extra else DEFAULT_TRUSTED_PATH
    dirs = []
    seen = set()
    for part in raw.split(os.pathsep):
        if not part or not os.path.isabs(part) or ".." in Path(part).parts:
            continue
        if part not in seen:
            seen.add(part)
            dirs.append(part)
    return dirs or ["/usr/bin", "/bin"]


def trusted_path_string():
    return os.pathsep.join(trusted_path_dirs())


def _is_trusted_real(real, dirs=None):
    for directory in dirs or trusted_path_dirs():
        if real == directory or real.startswith(directory + os.sep):
            return True
    return False


def resolve_trusted_exec(name):
    """Return an allowlisted absolute executable. Never search ambient PATH."""
    if not name or name in (".", "..") or os.sep in name:
        raise PublishError(f"Refusing unsafe tool name {name}.")
    dirs = trusted_path_dirs()
    for directory in dirs:
        candidate = os.path.join(directory, name)
        try:
            if not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
                continue
            real = os.path.realpath(candidate)
        except OSError:
            continue
        if _is_trusted_real(real, dirs):
            return candidate
    raise PublishError(
        f"Refusing to proceed without a trusted {name} (searched {trusted_path_string()})."
    )


def closed_env(*, session=False):
    env = {
        "PATH": trusted_path_string(),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    for key, value in os.environ.items():
        if key.startswith("UNDERPANTS_"):
            env[key] = value
    if session:
        for key in SESSION_ENV_KEYS:
            value = os.environ.get(key)
            if value:
                env[key] = value
    return env


def default_validator():
    return (resolve_trusted_exec("omarchy"), "plugin", "validate")


def wrapper_payload(*, pgrep, toggle, python3, env, screensaver):
    """Generate the idle launcher with install-time absolute tool identities."""
    return f"""#!/bin/bash
# Fixed-path Underpants idle launcher. Tools are pinned; environment is closed.
# Does not participate in PATH-based omarchy-launch-screensaver selection.
set -euo pipefail

pgrep={shlex.quote(pgrep)}
toggle={shlex.quote(toggle)}
python3={shlex.quote(python3)}
env={shlex.quote(env)}
screensaver={shlex.quote(screensaver)}

"$pgrep" -f '[o]rg.omarchy.screensaver' >/dev/null && exit 0

if "$toggle" screensaver-off && [[ ${{1:-}} != "force" ]]; then
  exit 1
fi

closed=(PATH=/usr/bin:/bin "HOME=$HOME")
[[ -n ${{USER-}} ]] && closed+=("USER=$USER")
[[ -n ${{LOGNAME-}} ]] && closed+=("LOGNAME=$LOGNAME")
[[ -n ${{LANG-}} ]] && closed+=("LANG=$LANG")
[[ -n ${{XDG_RUNTIME_DIR-}} ]] && closed+=("XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR")
[[ -n ${{XDG_SESSION_TYPE-}} ]] && closed+=("XDG_SESSION_TYPE=$XDG_SESSION_TYPE")
[[ -n ${{XDG_SESSION_ID-}} ]] && closed+=("XDG_SESSION_ID=$XDG_SESSION_ID")
[[ -n ${{WAYLAND_DISPLAY-}} ]] && closed+=("WAYLAND_DISPLAY=$WAYLAND_DISPLAY")
[[ -n ${{DISPLAY-}} ]] && closed+=("DISPLAY=$DISPLAY")
[[ -n ${{HYPRLAND_INSTANCE_SIGNATURE-}} ]] && closed+=("HYPRLAND_INSTANCE_SIGNATURE=$HYPRLAND_INSTANCE_SIGNATURE")
[[ -n ${{OMARCHY_PATH-}} ]] && closed+=("OMARCHY_PATH=$OMARCHY_PATH")
[[ -n ${{UNDERPANTS_MODE-}} ]] && closed+=("UNDERPANTS_MODE=$UNDERPANTS_MODE")

exec "$env" -i "${{closed[@]}}" "$python3" "$screensaver" \\
  --launch --mode "${{UNDERPANTS_MODE:-story}}"
"""


def resolve_wrapper_tools():
    return {
        "pgrep": resolve_trusted_exec("pgrep"),
        "toggle": resolve_trusted_exec("omarchy-toggle-enabled"),
        "python3": resolve_trusted_exec("python3"),
        "env": resolve_trusted_exec("env"),
    }


def require_nofollow_support():
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_EXCL"):
        raise PublishError("Refusing to publish without no-follow exclusive open support.")


def _require_dir(fd, label, *, owned=False):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise PublishError(f"Refusing to use {label}: not a directory.")
    if owned and info.st_uid != os.geteuid():
        raise PublishError(f"Refusing to use {label}: unexpected owner.")
    return info


def _blocking(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
    return fd


def _require_staged_file(fd, data, label):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise PublishError(f"Refusing staged {label}: not a regular file.")
    if info.st_uid != os.geteuid():
        raise PublishError(f"Refusing staged {label}: unexpected owner.")
    if info.st_nlink != 1:
        raise PublishError(f"Refusing staged {label}: unexpected link count.")
    os.lseek(fd, 0, os.SEEK_SET)
    if os.read(fd, len(data) + 1) != data:
        raise PublishError(f"Refusing staged {label}: payload mismatch.")
    return info


def _split_abs(path):
    if not path or not os.path.isabs(path) or "\x00" in path:
        raise PublishError("Refusing an unsafe path.")
    parts = Path(path).parts
    if parts[0] != os.sep:
        raise PublishError("Refusing an unsafe path.")
    names = parts[1:]
    if any(name in ("", ".", "..") for name in names):
        raise PublishError("Refusing a path with empty or parent components.")
    return names


def _open_root():
    try:
        return os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as error:
        raise PublishError("Refusing to open the filesystem root.") from error


def _open_child_dir(parent_fd, name, label, *, create=False, owned=False):
    if create:
        try:
            os.mkdir(name, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        except OSError as error:
            raise PublishError(f"Refusing to create {label}.") from error
    try:
        fd = os.open(name, DIR_OPEN_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        action = "create" if create else "open"
        raise PublishError(f"Refusing to {action} {label}.") from error
    try:
        _require_dir(fd, label, owned=owned)
    except Exception:
        os.close(fd)
        raise
    return fd


def _close_quietly(*fds):
    for fd in fds:
        if fd is not None:
            os.close(fd)


def traverse_abs(path, *, create_from=None, owned_from=None):
    """Open path, never following a symlink component.

    create_from / owned_from are 0-based indexes into the path components
    after the root (so owned_from=len(home_parts) means everything under HOME).
    """
    require_nofollow_support()
    names = _split_abs(path)
    fd = _open_root()
    try:
        for index, name in enumerate(names):
            label = os.sep + os.sep.join(names[: index + 1])
            child = _open_child_dir(
                fd, name, label,
                create=create_from is not None and index >= create_from,
                owned=owned_from is not None and index >= owned_from,
            )
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def open_home(home):
    home = os.path.expanduser(home)
    if home.endswith(os.sep) and home != os.sep:
        home = home.rstrip(os.sep)
    names = _split_abs(home)
    return home, names, traverse_abs(home, owned_from=len(names) - 1)


def _ensure_under_home(home_fd, home_names, rel):
    rel = Path(rel)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        raise PublishError("Refusing an unsafe relative path.")
    names = rel.parts
    fd = os.dup(home_fd)
    try:
        for offset, name in enumerate(names):
            label = os.sep + os.sep.join((*home_names, *names[: offset + 1]))
            child = _open_child_dir(fd, name, label, create=True, owned=True)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_under_home(home_fd, home_names, rel, *, last_is_file=False):
    rel = Path(rel)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        raise PublishError("Refusing an unsafe relative path.")
    names = rel.parts
    if not names:
        raise PublishError("Refusing an empty relative path.")
    fd = os.dup(home_fd)
    try:
        for offset, name in enumerate(names):
            label = os.sep + os.sep.join((*home_names, *names[: offset + 1]))
            last = offset == len(names) - 1
            if last and last_is_file:
                try:
                    child = os.open(name, FILE_PROBE_FLAGS, dir_fd=fd)
                except OSError as error:
                    raise PublishError(f"Refusing to open {label}.") from error
                os.close(fd)
                return child
            child = _open_child_dir(fd, name, label, create=False, owned=True)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def _exclusive_temp_name(prefix=TEMP_PREFIX):
    return prefix + secrets.token_hex(16)


def _exclusive_temp_file(parent_fd, *, prefix=TEMP_PREFIX, mode=0o600):
    for _ in range(64):
        name = _exclusive_temp_name(prefix)
        try:
            fd = os.open(name, FILE_CREATE_FLAGS, mode, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as error:
            raise PublishError("Refusing to create an exclusive temporary file.") from error
        try:
            return _blocking(fd), name
        except Exception:
            os.close(fd)
            try:
                os.unlink(name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
    raise PublishError("Refusing to create an exclusive temporary file.")


def _exclusive_temp_dir(parent_fd, *, prefix=TEMP_PREFIX, mode=0o755):
    for _ in range(64):
        name = _exclusive_temp_name(prefix)
        try:
            os.mkdir(name, mode, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as error:
            raise PublishError("Refusing to create an exclusive temporary directory.") from error
        try:
            fd = os.open(name, DIR_OPEN_FLAGS, dir_fd=parent_fd)
        except OSError:
            try:
                os.rmdir(name, dir_fd=parent_fd)
            except OSError:
                pass
            raise PublishError("Refusing to open an exclusive temporary directory.")
        try:
            _require_dir(fd, name, owned=True)
            return fd, name
        except Exception:
            os.close(fd)
            _remove_dir_contents(parent_fd, name)
            raise
    raise PublishError("Refusing to create an exclusive temporary directory.")


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise PublishError("Refusing a short write to a staged file.")
        view = view[written:]
    os.fsync(fd)


def _name_kind(parent_fd, name):
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None, None
    if stat.S_ISLNK(info.st_mode):
        return "symlink", info
    if stat.S_ISDIR(info.st_mode):
        return "dir", info
    if stat.S_ISREG(info.st_mode):
        return "file", info
    return "other", info


def _rename_noreplace(src_dir_fd, src_name, dst_dir_fd, dst_name):
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.renameat2(
        ctypes.c_int(src_dir_fd), os.fsencode(src_name),
        ctypes.c_int(dst_dir_fd), os.fsencode(dst_name),
        ctypes.c_uint(RENAME_NOREPLACE),
    )
    if result == 0:
        return
    err = ctypes.get_errno()
    if err in (errno.ENOSYS, errno.EINVAL):
        kind, _ = _name_kind(dst_dir_fd, dst_name)
        if kind is not None:
            raise FileExistsError(errno.EEXIST, "Destination exists")
        os.rename(src_name, dst_name, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        return
    raise OSError(err, os.strerror(err))


def _remove_dir_contents(parent_fd, name):
    try:
        fd = os.open(name, DIR_OPEN_FLAGS, dir_fd=parent_fd)
    except OSError:
        try:
            os.unlink(name, dir_fd=parent_fd)
        except OSError:
            pass
        return
    try:
        for child in os.listdir(fd):
            kind, _ = _name_kind(fd, child)
            if kind == "dir":
                _remove_dir_contents(fd, child)
            else:
                try:
                    os.unlink(child, dir_fd=fd)
                except OSError:
                    pass
        os.rmdir(name, dir_fd=parent_fd)
    finally:
        os.close(fd)


def publish_file(parent_fd, dest_name, data, *, mode=0o644, replace=False, label=None):
    """Stage data in an exclusive no-follow temp and publish it atomically."""
    label = label or dest_name
    kind, _ = _name_kind(parent_fd, dest_name)
    if kind == "symlink":
        raise PublishError(f"Refusing to replace a symlink at {label}.")
    if kind == "dir":
        raise PublishError(f"Refusing to replace a directory at {label}.")
    if kind == "other":
        raise PublishError(f"Refusing an unexpected existing {label}.")
    if kind == "file" and not replace:
        raise PublishError(f"Refusing an unexpected existing {label}.")

    fd = tmp_name = None
    try:
        fd, tmp_name = _exclusive_temp_file(parent_fd)
        _write_all(fd, data)
        os.fchmod(fd, mode)
        os.fsync(fd)
        _require_staged_file(fd, data, label)
        os.close(fd)
        fd = None
        if replace and kind == "file":
            os.rename(tmp_name, dest_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        else:
            try:
                _rename_noreplace(parent_fd, tmp_name, parent_fd, dest_name)
            except FileExistsError as error:
                raise PublishError(f"Refusing an unexpected existing {label}.") from error
            except OSError as error:
                if error.errno == errno.EEXIST:
                    raise PublishError(f"Refusing an unexpected existing {label}.") from error
                raise PublishError(f"Refusing to publish {label}.") from error
        tmp_name = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass

    published, _ = _name_kind(parent_fd, dest_name)
    if published != "file":
        raise PublishError(f"Refusing published {label}: not a regular file.")
    check = os.open(dest_name, FILE_PROBE_FLAGS, dir_fd=parent_fd)
    try:
        _blocking(check)
        _require_staged_file(check, data, label)
        os.fchmod(check, mode)
    finally:
        os.close(check)


def _copy_tree_nofollow(src_fd, dst_fd):
    for name in os.listdir(src_fd):
        kind, info = _name_kind(src_fd, name)
        if kind == "dir":
            os.mkdir(name, stat.S_IMODE(info.st_mode) or 0o755, dir_fd=dst_fd)
            child_src = child_dst = None
            try:
                child_src = os.open(name, DIR_OPEN_FLAGS, dir_fd=src_fd)
                child_dst = os.open(name, DIR_OPEN_FLAGS, dir_fd=dst_fd)
                _require_dir(child_src, name, owned=True)
                _require_dir(child_dst, name, owned=True)
                _copy_tree_nofollow(child_src, child_dst)
            finally:
                _close_quietly(child_src, child_dst)
            continue
        if kind != "file":
            raise PublishError(f"Refusing to back up unexpected entry {name}.")
        src = os.open(name, FILE_PROBE_FLAGS, dir_fd=src_fd)
        try:
            _blocking(src)
            data = b""
            while True:
                chunk = os.read(src, 1024 * 1024)
                if not chunk:
                    break
                data += chunk
            publish_file(dst_fd, name, data, mode=stat.S_IMODE(info.st_mode) or 0o644, replace=False, label=name)
        finally:
            os.close(src)


def _read_source_files(source_dir):
    source_fd = traverse_abs(source_dir, owned_from=None)
    try:
        files = {}
        for name in PLUGIN_FILES:
            if "/" in name or name in (".", ".."):
                raise PublishError(f"Refusing source name {name}.")
            fd = os.open(name, FILE_PROBE_FLAGS, dir_fd=source_fd)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise PublishError(f"Refusing source {name}: not a regular file.")
                _blocking(fd)
                data = b""
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    data += chunk
                files[name] = data
            finally:
                os.close(fd)
        return files
    finally:
        os.close(source_fd)


def _validate_plugin_fd(plugin_fd, validator):
    if not validator:
        return
    # Child /proc/self is the validator, not this process. The parent pid fd
    # still names the inode we hold.
    path = f"/proc/{os.getpid()}/fd/{plugin_fd}"
    result = subprocess.run(
        [*validator, path], capture_output=True, text=True, env=closed_env(),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "validator failed").strip()
        raise PublishError(detail or "Plugin validation failed.")


def _has_git(plugin_fd):
    try:
        fd = os.open(".git", FILE_PROBE_FLAGS, dir_fd=plugin_fd)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    os.close(fd)
    return True


def publish_plugin(source_dir, home, *, force=False, validator=None):
    source_dir = str(Path(source_dir))
    if validator is None:
        validator = default_validator()
    files = _read_source_files(source_dir)
    home_path, home_names, home_fd = open_home(home)
    plugins_rel = PLUGIN_REL.parent
    plugin_name = PLUGIN_REL.name
    plugins_fd = backup_parent_fd = None
    backup_message = None
    try:
        plugins_fd = _ensure_under_home(home_fd, home_names, plugins_rel)
        kind, _ = _name_kind(plugins_fd, plugin_name)
        if kind == "symlink":
            raise PublishError(
                "Refusing to overwrite a symlink or Git-managed plugin; update that checkout separately."
            )
        if kind == "other":
            raise PublishError("Refusing an unexpected existing plugin entry.")
        if kind == "file":
            raise PublishError("Refusing an unexpected existing plugin entry.")
        if kind is None:
            staged_fd, staged_name = _exclusive_temp_dir(plugins_fd)
            try:
                for name, data in files.items():
                    publish_file(staged_fd, name, data, mode=0o644, replace=False, label=name)
                for name, data in files.items():
                    check = os.open(name, FILE_PROBE_FLAGS, dir_fd=staged_fd)
                    try:
                        _blocking(check)
                        _require_staged_file(check, data, name)
                    finally:
                        os.close(check)
                _validate_plugin_fd(staged_fd, validator)
                try:
                    _rename_noreplace(plugins_fd, staged_name, plugins_fd, plugin_name)
                except FileExistsError as error:
                    raise PublishError(
                        "A local plugin already exists. Use --force to back it up and replace it."
                    ) from error
                except OSError as error:
                    if error.errno == errno.EEXIST:
                        raise PublishError(
                            "A local plugin already exists. Use --force to back it up and replace it."
                        ) from error
                    raise PublishError("Refusing to publish the plugin directory.") from error
                staged_name = None
            finally:
                os.close(staged_fd)
                if staged_name is not None:
                    _remove_dir_contents(plugins_fd, staged_name)
            return Path(home_path) / PLUGIN_REL, backup_message

        target_fd = os.open(plugin_name, DIR_OPEN_FLAGS, dir_fd=plugins_fd)
        try:
            _require_dir(target_fd, str(PLUGIN_REL), owned=True)
            if _has_git(target_fd):
                raise PublishError(
                    "Refusing to overwrite a symlink or Git-managed plugin; update that checkout separately."
                )
            if not force:
                raise PublishError("A local plugin already exists. Use --force to back it up and replace it.")
            _validate_plugin_fd(target_fd, validator)
            backup_parent_fd = _ensure_under_home(home_fd, home_names, Path(".config") / "omarchy")
            backup_fd, backup_name = _exclusive_temp_dir(
                backup_parent_fd, prefix=BACKUP_PREFIX, mode=0o700,
            )
            try:
                plugin_backup_fd, plugin_backup_name = _exclusive_temp_dir(backup_fd, prefix="plugin-")
                try:
                    _copy_tree_nofollow(target_fd, plugin_backup_fd)
                    try:
                        _rename_noreplace(backup_fd, plugin_backup_name, backup_fd, "plugin")
                    except OSError as error:
                        raise PublishError("Refusing to publish the plugin backup.") from error
                    plugin_backup_name = None
                finally:
                    os.close(plugin_backup_fd)
                    if plugin_backup_name is not None:
                        _remove_dir_contents(backup_fd, plugin_backup_name)
            finally:
                os.close(backup_fd)
            backup_message = f"Saved previous plugin to {Path(home_path) / '.config' / 'omarchy' / backup_name / 'plugin'}"
            for name, data in files.items():
                publish_file(target_fd, name, data, mode=0o644, replace=True, label=name)
            _validate_plugin_fd(target_fd, validator)
        finally:
            os.close(target_fd)
        return Path(home_path) / PLUGIN_REL, backup_message
    finally:
        _close_quietly(plugins_fd, backup_parent_fd, home_fd)


def require_installed_plugin(home):
    home_path, home_names, home_fd = open_home(home)
    try:
        fd = _open_under_home(home_fd, home_names, PLUGIN_PY_REL, last_is_file=True)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise PublishError(f"Plugin not found at: {Path(home_path) / PLUGIN_PY_REL}")
        finally:
            os.close(fd)
    except PublishError as error:
        if "Plugin not found" in str(error):
            raise
        raise PublishError(f"Plugin not found at: {Path(home_path) / PLUGIN_PY_REL}") from error
    finally:
        os.close(home_fd)


def publish_wrapper(home, *, tools=None):
    require_installed_plugin(home)
    home_path, home_names, home_fd = open_home(home)
    tools = dict(tools or resolve_wrapper_tools())
    screensaver = str(Path(home_path) / PLUGIN_PY_REL)
    if not os.path.isabs(screensaver):
        raise PublishError("Refusing a non-absolute screensaver path.")
    payload = wrapper_payload(screensaver=screensaver, **tools).encode()
    bin_fd = None
    try:
        bin_fd = _ensure_under_home(home_fd, home_names, WRAPPER_REL.parent)
        publish_file(bin_fd, WRAPPER_NAME, payload, mode=0o755, replace=False, label=str(WRAPPER_REL))
        return Path(home_path) / WRAPPER_REL
    finally:
        _close_quietly(bin_fd, home_fd)


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Descriptor-safe installer publish helper.")
    sub = parser.add_subparsers(dest="command", required=True)
    plugin = sub.add_parser("install-plugin")
    plugin.add_argument("--source", required=True)
    plugin.add_argument("--home", required=True)
    plugin.add_argument("--force", action="store_true")
    plugin.add_argument("--validator", nargs="+", default=None)
    wrapper = sub.add_parser("install-wrapper")
    wrapper.add_argument("--home", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.command == "install-plugin":
            validator = tuple(args.validator) if args.validator is not None else None
            _, message = publish_plugin(
                args.source, args.home, force=args.force, validator=validator,
            )
            if message:
                print(message)
            return 0
        publish_wrapper(args.home)
        return 0
    except PublishError as error:
        print(str(error), file=sys.stderr)
        return error.status


if __name__ == "__main__":
    sys.exit(main())
