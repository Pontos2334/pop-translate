import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk

from ..i18n import (
    SETUP_TITLE, SETUP_DESCRIPTION,
    SETUP_API_KEY_LABEL, SETUP_API_URL_LABEL, SETUP_MODEL_LABEL,
    SETUP_VISION_MODEL_LABEL, SETUP_TIMEOUT_LABEL,
    SETUP_SAVE, SETUP_CANCEL, SETUP_API_KEY_REQUIRED, SETUP_TIMEOUT_INVALID,
)
from .widgets import icon_image, load_styles


class SetupDialog(Gtk.Window):
    def __init__(self, config, on_saved):
        super().__init__(title=SETUP_TITLE)
        self.config = config
        self.on_saved = on_saved
        self._saved_emitted = False

        self.set_default_size(460, -1)
        self.set_resizable(True)
        self._load_css()
        self._build_ui()

        self.connect("close-request", self._on_close_request)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

    def _load_css(self):
        load_styles()

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_css_classes(["setup-window"])
        self.set_child(outer)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_css_classes(["setup-content"])
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_min_content_height(140)
        display = Gdk.Display.get_default()
        monitors = display.get_monitors() if display is not None else None
        monitor = monitors.get_item(0) if monitors is not None and monitors.get_n_items() else None
        height = monitor.get_geometry().height if monitor is not None else 900
        scrolled.set_max_content_height(max(180, min(620, int(height * .8) - 80)))
        scrolled.set_child(content)
        scrolled.set_vexpand(True)
        outer.append(scrolled)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.set_css_classes(["setup-header"])
        mark = icon_image("translate-symbolic", 17)
        mark.set_css_classes(["app-mark"])
        mark.set_valign(Gtk.Align.CENTER)
        header.append(mark)

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.set_hexpand(True)
        title = Gtk.Label(label=SETUP_TITLE)
        title.set_css_classes(["setup-title"])
        title.set_halign(Gtk.Align.START)
        titles.append(title)

        description = Gtk.Label(label=SETUP_DESCRIPTION, xalign=0)
        description.set_css_classes(["setup-description"])
        description.set_wrap(True)
        titles.append(description)
        header.append(titles)
        content.append(header)

        self.key_entry = self._add_field(content, SETUP_API_KEY_LABEL, self.config.api_key, True)
        self.url_entry = self._add_field(content, SETUP_API_URL_LABEL, self.config.api_url, False)
        self.model_entry = self._add_field(content, SETUP_MODEL_LABEL, self.config.model, False)
        self.vision_model_entry = self._add_field(content, SETUP_VISION_MODEL_LABEL, self.config.vision_model, False)
        self.timeout_entry = self._add_field(content, SETUP_TIMEOUT_LABEL, str(self.config.timeout), False)

        # 用透明度切换而非显隐，避免错误出现/消失时把按钮栏顶来顶去
        self.error_label = Gtk.Label(label=" ")
        self.error_label.set_css_classes(["error-hint"])
        self.error_label.set_halign(Gtk.Align.START)
        self.error_label.set_wrap(True)
        self.error_label.set_opacity(0.0)
        content.append(self.error_label)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_bar.set_css_classes(["setup-footer"])
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_bar.append(spacer)

        cancel_btn = Gtk.Button(label=SETUP_CANCEL)
        cancel_btn.set_css_classes(["setup-cancel"])
        cancel_btn.connect("clicked", lambda b: self.close())
        btn_bar.append(cancel_btn)

        save_btn = Gtk.Button(label=SETUP_SAVE)
        save_btn.set_css_classes(["setup-save"])
        save_btn.connect("clicked", self._on_save)
        btn_bar.append(save_btn)

        outer.append(btn_bar)
        self.key_entry.grab_focus()

    def _add_field(self, parent, label_text, default_value, is_password):
        field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        field.set_css_classes(["setup-field"])
        parent.append(field)
        label = Gtk.Label(label=label_text)
        label.set_css_classes(["setup-label"])
        label.set_halign(Gtk.Align.START)
        field.append(label)

        entry = Gtk.Entry()
        entry.set_css_classes(["setup-entry"])
        entry.set_text(default_value)
        if is_password:
            entry.set_visibility(False)
            entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-reveal-symbolic")
            entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "显示或隐藏密钥")
            entry.connect("icon-release", self._toggle_key_visibility)
        field.append(entry)
        label.set_mnemonic_widget(entry)

        return entry

    def _toggle_key_visibility(self, entry, position):
        if position == Gtk.EntryIconPosition.SECONDARY:
            entry.set_visibility(not entry.get_visibility())

    def _show_error(self, message):
        self.error_label.set_label(message)
        self.error_label.set_opacity(1.0)

    def _hide_error(self):
        self.error_label.set_opacity(0.0)

    def _on_key(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._on_save(controller.get_widget())
            return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _on_save(self, btn):
        # 全部字段先校验，再统一写入 config，避免校验失败留下半更新的配置
        api_key = self.key_entry.get_text().strip()
        if not api_key:
            self._show_error(SETUP_API_KEY_REQUIRED)
            return

        timeout_text = self.timeout_entry.get_text().strip()
        try:
            timeout = int(timeout_text)
            if timeout <= 0:
                raise ValueError
        except ValueError:
            self._show_error(SETUP_TIMEOUT_INVALID)
            return

        self._hide_error()

        self.config.api_key = api_key
        self.config.api_url = self.url_entry.get_text().strip() or self.config.api_url
        self.config.model = self.model_entry.get_text().strip() or self.config.model
        self.config.vision_model = (
            self.vision_model_entry.get_text().strip() or self.config.vision_model
        )
        self.config.timeout = timeout
        self.config.save()
        self.close()

    def _emit_saved(self):
        if self._saved_emitted:
            return
        self._saved_emitted = True
        if self.on_saved:
            self.on_saved()

    def _on_close_request(self, _window):
        # close() 是唯一出口：保存路径与取消路径都恰好触发一次 on_saved
        self._emit_saved()
        return False
