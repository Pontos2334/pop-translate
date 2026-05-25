import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib

from .config import Config
from .clipboard import get_selection
from .history import HistoryDB
from .translate import translate
from .ui.window import TranslateWindow
from .ui.setup_dialog import SetupDialog


class TranslateApp(Gtk.Application):
    def __init__(self, text, config, history_db):
        super().__init__(application_id="com.translate.popup")
        self.text = text
        self.config = config
        self.history_db = history_db

    def do_activate(self):
        self.win = TranslateWindow(self, self.text, self.config, self.history_db)
        self.win.show_loading()
        self.win.present()
        GLib.idle_add(self._start_translate)

    def _start_translate(self):
        def worker():
            result = translate(self.text, self.config, self.history_db)
            GLib.idle_add(self._show_result, result)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return False

    def _show_result(self, result):
        self.win.show_translation(result)
        return False


def main():
    config = Config()
    config.load()

    if not config.has_api_key:
        app = Gtk.Application(application_id="com.translate.popup")
        history_db = HistoryDB()

        def on_activate(application):
            win = SetupDialog(config, lambda: None)
            win.set_application(application)
            win.present()

        app.connect("activate", on_activate)
        app.run(None)
        sys.exit(0)

    text = get_selection()
    if not text:
        sys.exit(0)

    history_db = HistoryDB()
    app = TranslateApp(text, config, history_db)
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
