import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib

from .config import Config
from .clipboard import get_selection
from .history import HistoryDB
from .translate import translate, explain, should_translate
from .ui.window import TranslateWindow
from .ui.setup_dialog import SetupDialog


class TranslateApp(Gtk.Application):
    def __init__(self, text, config, history_db, default_tab):
        super().__init__(application_id="com.translate.popup")
        self.text = text
        self.config = config
        self.history_db = history_db
        self.default_tab = default_tab

    def do_activate(self):
        self.win = TranslateWindow(self, self.text, self.config, self.history_db, self.default_tab)
        self.win.present()
        GLib.idle_add(self._start_fetch)

    def _start_fetch(self):
        threading.Thread(target=self._fetch_translate, daemon=True).start()
        threading.Thread(target=self._fetch_explain, daemon=True).start()
        return False

    def _fetch_translate(self):
        result = translate(self.text, self.config, self.history_db)
        GLib.idle_add(self.win.set_translation, result)

    def _fetch_explain(self):
        result = explain(self.text, self.config)
        GLib.idle_add(self.win.set_explanation, result)


def main():
    config = Config()
    config.load()

    if not config.has_api_key:
        app = Gtk.Application(application_id="com.translate.popup")

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

    default_tab = "translate" if should_translate(text) else "explain"
    history_db = HistoryDB()
    app = TranslateApp(text, config, history_db, default_tab)
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
