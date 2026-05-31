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
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"clipboard read error (wl-paste --primary): {e}", file=sys.stderr)
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
        print(f"clipboard read error (wl-paste): {e}", file=sys.stderr)
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
        print(f"clipboard read error (xclip primary): {e}", file=sys.stderr)
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
        print(f"clipboard read error (xclip clipboard): {e}", file=sys.stderr)
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
            print(f"clipboard copy error (wl-copy): {e}", file=sys.stderr)

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
        print(f"clipboard copy error (xclip): {e}", file=sys.stderr)

    return False
