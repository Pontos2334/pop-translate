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


def capture_screenshot(tmp_img=None):
    global _LAST_OCR_IMAGE
    import time
    tmp_img = tmp_img or _new_ocr_image_path()
    _LAST_OCR_IMAGE = tmp_img
    if os.path.exists(tmp_img):
        _cleanup_file(tmp_img)

    screenshot_tools = [
        ["spectacle", "-r", "-b", "-o", tmp_img],
        ["gnome-screenshot", "-a", "-f", tmp_img],
        ["scrot", "-s", tmp_img],
    ]

    cmd = None
    for tool_cmd in screenshot_tools:
        if shutil.which(tool_cmd[0]):
            cmd = tool_cmd
            break

    if cmd is None:
        print("未找到截图工具，请安装 spectacle、gnome-screenshot 或 scrot", file=sys.stderr)
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
            if not os.path.exists(tmp_img):
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


def main():
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

    # Check for CLI OCR flag
    text = ""
    ocr_bootstrapping = False
    if "--ocr" in sys.argv or "-o" in sys.argv:
        if not capture_screenshot():
            sys.exit(0)
        text = OCR_LOADING
        default_tab = "translate"
        ocr_bootstrapping = True
    else:
        simulate_copy()
        text = get_selection()
        if not text:
            sys.exit(0)

    # Copy original text to clipboard. OCR mode copies the recognized text after OCR finishes.
    if not ocr_bootstrapping:
        copy_text(text)

    # Route automatically to Explain if code or error message is detected
    if ocr_bootstrapping:
        default_tab = "translate"
    elif is_code_or_error(text):
        default_tab = "explain"
    else:
        default_tab = "translate" if should_translate(text) else "explain"

    history_db = HistoryDB()
    app = TranslateApp(text, config, history_db, default_tab, ocr_bootstrapping)
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
