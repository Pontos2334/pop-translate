import sys
import os
import subprocess
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio

from .config import Config
from .clipboard import get_selection
from .history import HistoryDB
from .translate import should_translate, is_code_or_error
from .ui.window import TranslateWindow
from .ui.setup_dialog import SetupDialog


_EASYOCR_READER = None


def perform_local_ocr():
    global _EASYOCR_READER
    # 1. Capture screen region using spectacle
    tmp_img = "/tmp/pop_translate_ocr.png"
    if os.path.exists(tmp_img):
        try:
            os.remove(tmp_img)
        except Exception:
            pass
            
    # Run spectacle in background mode to capture region
    try:
        subprocess.run([
            "spectacle", "-r", "-b", "-o", tmp_img
        ], check=True)
    except Exception as e:
        print(f"截图失败: {e}", file=sys.stderr)
        return ""
        
    if not os.path.exists(tmp_img):
        return ""
        
    # 2. Try EasyOCR first (GPU/CPU accelerated, highly accurate)
    try:
        import easyocr
        if _EASYOCR_READER is None:
            # Initializes EasyOCR and automatically handles GPU (CUDA/ROCm) vs CPU detection
            _EASYOCR_READER = easyocr.Reader(['ch_sim', 'en'], verbose=False)
        result = _EASYOCR_READER.readtext(tmp_img, detail=0)
        text = "\n".join(result).strip()
        
        # Clean up tmp image
        try:
            os.remove(tmp_img)
        except Exception:
            pass
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
            return ""
            
    # Clean up tmp image
    try:
        os.remove(tmp_img)
    except Exception:
        pass
        
    return text


class TranslateApp(Gtk.Application):
    def __init__(self, text, config, history_db, default_tab):
        super().__init__(
            application_id="com.translate.popup",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.text = text
        self.config = config
        self.history_db = history_db
        self.default_tab = default_tab

    def do_activate(self):
        self.win = TranslateWindow(self, self.text, self.config, self.history_db, self.default_tab)
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
    if "--ocr" in sys.argv or "-o" in sys.argv:
        text = perform_local_ocr()
        if not text:
            sys.exit(0)
    else:
        text = get_selection()
        if not text:
            sys.exit(0)

    # Route automatically to Explain if code or error message is detected
    if is_code_or_error(text):
        default_tab = "explain"
    else:
        default_tab = "translate" if should_translate(text) else "explain"

    history_db = HistoryDB()
    app = TranslateApp(text, config, history_db, default_tab)
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
