import glob
import json
import os
import subprocess
import stat

from .log import get_logger

logger = get_logger(__name__)


def _is_wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


def _read_wl_paste():
    try:
        r = subprocess.run(
            ["wl-paste", "--primary", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "")},
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("clipboard read error (wl-paste --primary): %s", e)
    return ""


def _read_wl_clipboard():
    try:
        r = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "")},
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("clipboard read error (wl-paste): %s", e)
    return ""


def _read_xclip():
    try:
        r = subprocess.run(
            ["xclip", "-selection", "primary", "-o"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("clipboard read error (xclip primary): %s", e)
    return ""


def _read_xclip_clipboard():
    try:
        r = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("clipboard read error (xclip clipboard): %s", e)
    return ""


def get_selection():
    if _is_wayland():
        text = _read_wl_clipboard()
        if not text:
            text = _read_wl_paste()
        return text
    text = _read_xclip_clipboard()
    if not text:
        text = _read_xclip()
    return text


def _kitty_remote_addresses():
    addresses = []

    def add(address):
        if address and address not in addresses:
            addresses.append(address)

    env_address = os.environ.get("KITTY_LISTEN_ON", "")
    if env_address:
        if env_address.startswith(("unix:", "tcp:")):
            add(env_address)
        else:
            add(f"unix:{env_address}")

    tmpdir = os.environ.get("TMPDIR") or "/tmp"
    for path in glob.glob(os.path.join(tmpdir, "mykitty*")):
        try:
            info = os.stat(path)
        except OSError:
            continue
        if info.st_uid != os.getuid() or not stat.S_ISSOCK(info.st_mode):
            continue
        add(f"unix:{path}")

    return addresses


def _kitty_has_focused_window(address):
    try:
        result = subprocess.run(
            ["kitty", "@", "--to", address, "ls"],
            capture_output=True,
            text=True,
            timeout=0.6,
        )
    except FileNotFoundError:
        return False
    except Exception:
        return False

    if result.returncode != 0:
        return False

    try:
        windows = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False

    return any(window.get("is_focused") for window in windows)


def _copy_with_focused_kitty():
    for address in _kitty_remote_addresses():
        if not _kitty_has_focused_window(address):
            continue
        try:
            result = subprocess.run(
                ["kitty", "@", "--to", address, "action", "--match", "state:focused", "copy_to_clipboard"],
                timeout=0.6,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            continue
        if result.returncode == 0:
            return True
    return False


def simulate_copy():
    if _is_wayland():
        if _copy_with_focused_kitty():
            return
        try:
            subprocess.run(
                ["ydotool", "key", "29:1", "110:1", "110:0", "29:0"],
                timeout=1,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass
        except Exception:
            pass
    else:
        try:
            subprocess.run(
                ["xdotool", "key", "ctrl+Insert"],
                timeout=1,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass
        except Exception:
            pass


def copy_text(text):
    if _is_wayland():
        try:
            subprocess.run(
                ["wl-copy"],
                input=text,
                text=True,
                timeout=2,
                env={**os.environ, "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "")},
            )
            return True
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("clipboard copy error (wl-copy): %s", e)

    try:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text,
            text=True,
            timeout=2,
        )
        return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("clipboard copy error (xclip): %s", e)

    return False
