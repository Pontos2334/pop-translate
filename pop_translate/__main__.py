import argparse
import shutil
import sys
import os
import subprocess
import tempfile
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio

from .config import Config
from .clipboard import get_selection, copy_text, simulate_copy
from .history import HistoryDB
from .translate import should_translate, is_code_or_error
from .i18n import OCR_LOADING
from .ui.window import TranslateWindow
from .ui.setup_dialog import SetupDialog


_EASYOCR_READER = None
_LAST_OCR_IMAGE = None


def _new_ocr_image_path():
    fd, path = tempfile.mkstemp(prefix="pop_translate_ocr_", suffix=".png")
    os.close(fd)
    try:
        os.remove(path)
    except OSError:
        pass
    return path


def _cleanup_file(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _command_exists(command):
    if os.path.isabs(command):
        return os.path.exists(command) and os.access(command, os.X_OK)
    return shutil.which(command) is not None


def _snipaste_executable():
    for name in ("Snipaste", "snipaste"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _is_snipaste_running():
    names = ("Snipaste", "snipaste")
    for name in names:
        try:
            if subprocess.run(
                ["pgrep", "-x", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1,
            ).returncode == 0:
                return True
        except Exception:
            pass
    return False


def _ensure_snipaste_running(executable):
    if _is_snipaste_running():
        return True
    try:
        subprocess.Popen(
            [executable],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False

    import time
    for _ in range(20):
        if _is_snipaste_running():
            return True
        time.sleep(0.1)
    return False


def capture_screenshot(tmp_img=None):
    global _LAST_OCR_IMAGE
    import time
    tmp_img = tmp_img or _new_ocr_image_path()
    _LAST_OCR_IMAGE = tmp_img
    if os.path.exists(tmp_img):
        _cleanup_file(tmp_img)

    screenshot_tools = []
    snipaste = _snipaste_executable()
    if snipaste and _ensure_snipaste_running(snipaste):
        screenshot_tools.append(([snipaste, "snip", "-o", tmp_img], True))

    screenshot_tools.extend([
        (["spectacle", "-r", "-b", "-o", tmp_img], False),
        (["gnome-screenshot", "-a", "-f", tmp_img], False),
        (["scrot", "-s", tmp_img], False),
    ])

    cmd = None
    waits_after_exit = False
    for tool_cmd, tool_waits_after_exit in screenshot_tools:
        if _command_exists(tool_cmd[0]):
            cmd = tool_cmd
            waits_after_exit = tool_waits_after_exit
            break

    if cmd is None:
        print("未找到截图工具，请安装并启动 Snipaste，或安装 spectacle、gnome-screenshot 或 scrot", file=sys.stderr)
        _cleanup_file(tmp_img)
        return False

    try:
        proc = subprocess.Popen(cmd)
    except Exception as e:
        print(f"截图失败: {e}", file=sys.stderr)
        _cleanup_file(tmp_img)
        return False

    start_time = time.time()
    timeout = 120.0

    while time.time() - start_time < timeout:
        if proc.poll() is not None:
            if not waits_after_exit and not os.path.exists(tmp_img):
                _cleanup_file(tmp_img)
                return False
            if waits_after_exit and proc.returncode not in (0, None) and not os.path.exists(tmp_img):
                _cleanup_file(tmp_img)
                return False

        if os.path.exists(tmp_img):
            time.sleep(0.1)
            if os.path.getsize(tmp_img) > 0:
                return True

        time.sleep(0.05)

    if proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    _cleanup_file(tmp_img)
    return False


def ocr_image(tmp_img=None):
    global _EASYOCR_READER
    tmp_img = tmp_img or _LAST_OCR_IMAGE
    if not tmp_img or not os.path.exists(tmp_img):
        return ""
        
    # 2. Try EasyOCR first (GPU/CPU accelerated, highly accurate)
    try:
        import easyocr
        if _EASYOCR_READER is None:
            # Initializes EasyOCR and automatically handles GPU (CUDA/ROCm) vs CPU detection
            _EASYOCR_READER = easyocr.Reader(['ch_sim', 'en'], verbose=False)
        result = _EASYOCR_READER.readtext(tmp_img, detail=0, paragraph=True)
        text = "\n".join(result).strip()
        
        # Clean up tmp image
        _cleanup_file(tmp_img)
        return text
    except ImportError:
        # EasyOCR not installed, fallback silently to Tesseract
        pass
    except Exception as e:
        print(f"EasyOCR 识别出错 (将使用 Tesseract 备用): {e}", file=sys.stderr)

    # 3. Run local OCR using tesseract (CPU only, fallback)
    try:
        res = subprocess.run([
            "tesseract", tmp_img, "stdout", "-l", "eng+chi_sim"
        ], capture_output=True, text=True, check=True)
        text = res.stdout.strip()
    except Exception:
        try:
            # Fallback to default local language data
            res = subprocess.run([
                "tesseract", tmp_img, "stdout"
            ], capture_output=True, text=True, check=True)
            text = res.stdout.strip()
        except Exception as e:
            print(f"OCR 识别失败: {e}", file=sys.stderr)
            text = ""
            
    # Clean up tmp image
    _cleanup_file(tmp_img)
        
    return text


def perform_local_ocr():
    if capture_screenshot():
        return ocr_image()
    return ""


class TranslateApp(Gtk.Application):
    def __init__(self, text, config, history_db, default_tab, ocr_bootstrapping=False):
        super().__init__(
            application_id="com.translate.popup",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.text = text
        self.config = config
        self.history_db = history_db
        self.default_tab = default_tab
        self.ocr_bootstrapping = ocr_bootstrapping

    def do_activate(self):
        self.win = TranslateWindow(self, self.text, self.config, self.history_db, self.default_tab, self.ocr_bootstrapping)
        self.win.present()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="pop-translate",
        description="Show a Pop Translate popup for selected or supplied text.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("-o", "--ocr", action="store_true", help="capture an area and OCR it")
    source.add_argument("--text", help="use this text directly instead of reading the clipboard")
    parser.add_argument(
        "--tab",
        choices=("auto", "translate", "explain", "chat"),
        default="auto",
        help="default tab to open when text is supplied",
    )
    return parser.parse_args(argv)


def resolve_default_tab(text, requested_tab="auto", ocr_bootstrapping=False):
    if requested_tab != "auto":
        return requested_tab
    if ocr_bootstrapping:
        return "translate"
    if is_code_or_error(text):
        return "explain"
    return "translate" if should_translate(text) else "explain"


def run_popup(text, config, default_tab, ocr_bootstrapping=False):
    history_db = HistoryDB()
    app = TranslateApp(text, config, history_db, default_tab, ocr_bootstrapping)
    return app.run(None)


def main(argv=None):
    args = parse_args(argv)
    config = Config()
    config.load()

    if not config.has_api_key:
        app = Gtk.Application(
            application_id="com.translate.popup",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )

        def on_activate(application):
            win = SetupDialog(config, application.quit)
            win.set_application(application)
            win.present()

        app.connect("activate", on_activate)
        app.run(None)
        sys.exit(0)

    text = ""
    ocr_bootstrapping = False
    should_copy_original = False
    if args.ocr:
        if not capture_screenshot():
            sys.exit(0)
        text = OCR_LOADING
        ocr_bootstrapping = True
    elif args.text is not None:
        text = args.text.strip()
        if not text:
            sys.exit(0)
    else:
        simulate_copy()
        text = get_selection()
        if not text:
            sys.exit(0)
        should_copy_original = True

    # Copy original text only for the classic selection hotkey path. Direct text
    # integrations such as calibre URL handling should not overwrite clipboard.
    if should_copy_original:
        copy_text(text)

    default_tab = resolve_default_tab(text, args.tab, ocr_bootstrapping)
    sys.exit(run_popup(text, config, default_tab, ocr_bootstrapping))


if __name__ == "__main__":
    main()
