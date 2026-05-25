import subprocess
import os
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib

from ..css import CSS
from ..i18n import (
    APP_TITLE, TRANSLATING, EXPLAINING,
    BTN_EXPLAIN, BTN_EXPLAINING, BTN_EXPLAINED,
    BTN_COPY, BTN_COPIED,
)
from ..translate import translate, explain


class TranslateWindow(Gtk.ApplicationWindow):
    def __init__(self, app, text, config, history_db):
        super().__init__(application=app, title="translate")
        self.text = text
        self.translated = ""
        self.explaining = False
        self.config = config
        self.history_db = history_db
        self._loading_label = None

        self.set_decorated(False)
        self.set_resizable(True)
        self.set_default_size(480, 200)
        self.set_keep_above(True)

        self._load_css()
        self._build_ui()

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_css_classes(["translate-window"])
        self.set_child(outer)

        title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        title_bar.set_css_classes(["title-bar"])

        title_label = Gtk.Label(label=f" {APP_TITLE}")
        title_label.set_css_classes(["title-label"])
        title_label.set_halign(Gtk.Align.START)
        title_label.set_hexpand(True)
        title_bar.append(title_label)

        close_btn = Gtk.Button(label="✕")
        close_btn.set_css_classes(["close-btn"])
        close_btn.connect("clicked", lambda b: self.close())
        title_bar.append(close_btn)

        outer.append(title_bar)

        sep = Gtk.Box()
        sep.set_css_classes(["sep"])
        outer.append(sep)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_has_frame(False)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_propagate_natural_height(True)
        self.scrolled.set_min_content_width(460)
        self.scrolled.set_min_content_height(80)
        self.scrolled.set_max_content_height(900)
        outer.append(self.scrolled)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.content_box.set_css_classes(["content-box"])
        self.content_box.set_halign(Gtk.Align.FILL)
        self.content_box.set_valign(Gtk.Align.START)
        self.scrolled.set_child(self.content_box)

    def show_loading(self):
        self._clear_content()
        display = self._truncate(self.text)
        self._add_label(display, "orig")
        self._add_sep()
        self._loading_label = Gtk.Label(label=TRANSLATING)
        self._loading_label.set_css_classes(["hint"])
        self._loading_label.set_wrap(True)
        self._loading_label.set_xalign(0)
        self._loading_label.set_max_width_chars(55)
        self.content_box.append(self._loading_label)
        self._resize_to_content()

    def show_translation(self, translated):
        self._clear_content()
        self.translated = translated
        self._loading_label = None

        display = self._truncate(self.text)
        self._add_label(display, "orig")
        self._add_sep()
        self._add_label(translated, "result")
        self._add_button_bar()
        self._resize_to_content()

    def show_explanation(self, explanation):
        self._remove_loading()
        self._add_sep()

        title = Gtk.Label(label="解释：")
        title.set_css_classes(["explain-title"])
        title.set_wrap(True)
        title.set_xalign(0)
        title.set_max_width_chars(55)
        self.content_box.append(title)

        body = Gtk.Label(label=explanation)
        body.set_css_classes(["explain-body"])
        body.set_wrap(True)
        body.set_xalign(0)
        body.set_max_width_chars(55)
        self.content_box.append(body)

        self.explain_btn.set_sensitive(False)
        self.explain_btn.set_label(BTN_EXPLAINED)
        self.explaining = False
        self._resize_to_content()

    def _add_button_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_css_classes(["button-bar"])
        bar.set_halign(Gtk.Align.END)

        self.explain_btn = Gtk.Button(label=BTN_EXPLAIN)
        self.explain_btn.set_css_classes(["action-btn"])
        self.explain_btn.connect("clicked", self._on_explain)
        bar.append(self.explain_btn)

        copy_btn = Gtk.Button(label=BTN_COPY)
        copy_btn.set_css_classes(["action-btn", "copy"])
        copy_btn.connect("clicked", self._on_copy)
        bar.append(copy_btn)

        self.content_box.append(bar)

    def _on_explain(self, btn):
        if self.explaining:
            return
        self.explaining = True
        btn.set_label(BTN_EXPLAINING)
        btn.set_sensitive(False)

        self._loading_label = Gtk.Label(label=EXPLAINING)
        self._loading_label.set_css_classes(["hint"])
        self._loading_label.set_xalign(0)
        self.content_box.append(self._loading_label)

        def worker():
            result = explain(self.text, self.config)
            GLib.idle_add(self._on_explanation_done, result)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_explanation_done(self, result):
        self._remove_loading()
        self.show_explanation(result)
        return False

    def _on_copy(self, btn):
        subprocess.run(
            ["wl-copy", self.translated],
            capture_output=True,
            timeout=2,
            env={**os.environ, "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "")},
        )
        btn.set_label(BTN_COPIED)
        btn.set_sensitive(False)
        btn.remove_css_class("copy")

    def _remove_loading(self):
        if self._loading_label is not None:
            self.content_box.remove(self._loading_label)
            self._loading_label = None

    def _add_label(self, text, css_class):
        label = Gtk.Label(label=text)
        label.set_css_classes([css_class])
        label.set_wrap(True)
        label.set_xalign(0)
        label.set_max_width_chars(55)
        self.content_box.append(label)

    def _add_sep(self):
        s = Gtk.Box()
        s.set_css_classes(["sep"])
        self.content_box.append(s)

    def _resize_to_content(self):
        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        max_h = 900
        if monitors.get_n_items() > 0:
            m = monitors.get_item(0)
            geo = m.get_geometry()
            max_h = int(geo.height * 0.5)

        self.scrolled.set_max_content_height(max_h)
        self.scrolled.set_min_content_height(80)
        self.set_default_size(480, -1)

    def _truncate(self, text):
        max_chars = 300
        return text if len(text) <= max_chars else text[:max_chars] + "..."

    def _clear_content(self):
        while True:
            child = self.content_box.get_first_child()
            if child is None:
                break
            self.content_box.remove(child)
        self._loading_label = None

    def _on_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
