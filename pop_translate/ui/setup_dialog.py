import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk

from ..css import CSS
from ..i18n import (
    SETUP_TITLE,
    SETUP_API_KEY_LABEL, SETUP_API_URL_LABEL, SETUP_MODEL_LABEL,
    SETUP_SAVE, SETUP_CANCEL, SETUP_API_KEY_REQUIRED,
)


class SetupDialog(Gtk.Window):
    def __init__(self, config, on_saved):
        super().__init__(title=SETUP_TITLE)
        self.config = config
        self.on_saved = on_saved

        self.set_default_size(420, 300)
        self.set_resizable(False)
        self._load_css()
        self._build_ui()

        self.connect("close-request", self._on_close_request)

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_css_classes(["setup-window"])
        self.set_child(outer)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        outer.append(content)

        title = Gtk.Label(label=SETUP_TITLE)
        title.set_css_classes(["setup-title"])
        title.set_halign(Gtk.Align.START)
        content.append(title)

        sep = Gtk.Box()
        sep.set_css_classes(["sep"])
        content.append(sep)

        self.key_entry = self._add_field(content, SETUP_API_KEY_LABEL, "", True)
        self.url_entry = self._add_field(content, SETUP_API_URL_LABEL, self.config.api_url, False)
        self.model_entry = self._add_field(content, SETUP_MODEL_LABEL, self.config.model, False)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error-hint"])
        self.error_label.set_halign(Gtk.Align.START)
        self.error_label.set_visible(False)
        content.append(self.error_label)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_bar.set_halign(Gtk.Align.END)
        btn_bar.set_margin_top(8)

        cancel_btn = Gtk.Button(label=SETUP_CANCEL)
        cancel_btn.set_css_classes(["setup-cancel"])
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_bar.append(cancel_btn)

        save_btn = Gtk.Button(label=SETUP_SAVE)
        save_btn.set_css_classes(["setup-save"])
        save_btn.connect("clicked", self._on_save)
        btn_bar.append(save_btn)

        content.append(btn_bar)

    def _add_field(self, parent, label_text, default_value, is_password):
        label = Gtk.Label(label=label_text)
        label.set_css_classes(["setup-label"])
        label.set_halign(Gtk.Align.START)
        parent.append(label)

        entry = Gtk.Entry()
        entry.set_css_classes(["setup-entry"])
        entry.set_text(default_value)
        if is_password:
            entry.set_visibility(False)
        entry.set_margin_bottom(4)
        parent.append(entry)

        return entry

    def _on_save(self, btn):
        api_key = self.key_entry.get_text().strip()
        if not api_key:
            self.error_label.set_text(SETUP_API_KEY_REQUIRED)
            self.error_label.set_visible(True)
            return

        self.config.api_key = api_key
        self.config.api_url = self.url_entry.get_text().strip() or self.config.api_url
        self.config.model = self.model_entry.get_text().strip() or self.config.model
        self.config.save()

        self.close()
        if self.on_saved:
            self.on_saved()

    def _on_close_request(self, _window):
        if self.on_saved:
            self.on_saved()
        return False
