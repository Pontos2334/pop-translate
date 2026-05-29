import os
import subprocess


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
    except Exception:
        pass
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
    except Exception:
        pass
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
    except Exception:
        pass
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
    except Exception:
        pass
    return ""


def get_selection():
    if _is_wayland():
        text = _read_wl_paste()
        if not text:
            text = _read_wl_clipboard()
        return text
    text = _read_xclip()
    if not text:
        text = _read_xclip_clipboard()
    return text
