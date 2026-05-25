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
    BTN_COPY, BTN_COPIED, BTN_EDIT, BTN_RETRANSLATE, BTN_CANCEL, BTN_SEND,
    TAB_TRANSLATE, TAB_EXPLAIN, TAB_CHAT,
    SHORTCUT_HINT, CHAT_PLACEHOLDER, CHAT_THINKING,
)
from ..translate import translate, explain, chat as do_chat


class TranslateWindow(Gtk.ApplicationWindow):
    def __init__(self, app, text, config, history_db, default_tab="translate"):
        super().__init__(application=app, title="translate")
        self.original_text = text
        self.text = text
        self.translated = ""
        self.explanation = ""
        self.chat_messages = []
        self.config = config
        self.history_db = history_db
        self._loading_label = None
        self._default_tab = default_tab
        self._editing = False

        self.set_decorated(False)
        self.set_resizable(True)
        self.set_default_size(480, 320)

        self._load_css()
        self._build_ui()
        self._switch_tab(default_tab)

        self.connect("close-request", self._on_close)
        self.connect("realize", self._on_realize)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

    def _on_close(self, _window):
        self.get_application().quit()
        return False

    def _on_realize(self, widget):
        GLib.idle_add(self._focus_window)

    def _focus_window(self):
        self.present()
        return False

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        self.outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.outer.set_css_classes(["translate-window"])
        self.set_child(self.outer)

        self._build_title_bar()
        self._build_tab_bar()

        self.content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.outer.append(self.content_area)

        self._build_shortcut_bar()
        self._resize_to_content()

    def _build_title_bar(self):
        title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        title_bar.set_css_classes(["title-bar"])
        drag_gesture = Gtk.GestureClick.new()
        drag_gesture.set_button(1)
        drag_gesture.connect("pressed", self._on_title_bar_pressed)
        title_bar.add_controller(drag_gesture)

        title_label = Gtk.Label(label=f" {APP_TITLE}")
        title_label.set_css_classes(["title-label"])
        title_label.set_halign(Gtk.Align.START)
        title_label.set_hexpand(True)
        title_bar.append(title_label)

        self.edit_btn = Gtk.Button(label=BTN_EDIT)
        self.edit_btn.set_css_classes(["title-btn"])
        self.edit_btn.connect("clicked", self._on_edit)
        title_bar.append(self.edit_btn)

        close_btn = Gtk.Button(label="✕")
        close_btn.set_css_classes(["close-btn"])
        close_btn.connect("clicked", lambda b: self.close())
        title_bar.append(close_btn)

        self.outer.append(title_bar)

    def _on_title_bar_pressed(self, gesture, n_press, x, y):
        picked = gesture.get_widget().pick(x, y, Gtk.PickFlags.DEFAULT)
        while picked:
            if isinstance(picked, Gtk.Button):
                return
            picked = picked.get_parent()
        event = gesture.get_current_event()
        device = event.get_device() if event else None
        timestamp = event.get_time() if event else Gdk.CURRENT_TIME
        surface = self.get_surface()
        if surface and device:
            surface.begin_move(device, 1, x, y, timestamp)

    def _build_tab_bar(self):
        self.tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.tab_bar.set_css_classes(["tab-bar"])

        self.tab_btns = {}
        for tab_id, label in [("translate", TAB_TRANSLATE), ("explain", TAB_EXPLAIN), ("chat", TAB_CHAT)]:
            btn = Gtk.Button(label=label)
            btn.set_css_classes(["tab-btn"])
            btn.connect("clicked", lambda b, t=tab_id: self._switch_tab(t))
            self.tab_bar.append(btn)
            self.tab_btns[tab_id] = btn

        self.outer.append(self.tab_bar)

    def _build_shortcut_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bar.set_css_classes(["shortcut-bar"])
        hint = Gtk.Label(label=SHORTCUT_HINT)
        hint.set_css_classes(["shortcut-hint"])
        hint.set_halign(Gtk.Align.START)
        bar.append(hint)
        self.outer.append(bar)

    def _clear_content(self):
        while True:
            child = self.content_area.get_first_child()
            if child is None:
                break
            self.content_area.remove(child)
        self._loading_label = None

    def _switch_tab(self, tab_id):
        self._current_tab = tab_id
        for tid, btn in self.tab_btns.items():
            if tid == tab_id:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

        self._clear_content()

        if tab_id == "translate":
            self._show_translate_tab()
        elif tab_id == "explain":
            self._show_explain_tab()
        elif tab_id == "chat":
            self._show_chat_tab()

        self._resize_to_content()

    def _show_translate_tab(self):
        if self._editing:
            self._show_edit_mode()
            return

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])

        orig = Gtk.Label(label=self._truncate(self.text))
        orig.set_css_classes(["orig"])
        orig.set_wrap(True)
        orig.set_xalign(0)
        orig.set_max_width_chars(55)
        box.append(orig)

        sep = Gtk.Box()
        sep.set_css_classes(["sep"])
        box.append(sep)

        if self.translated:
            result = Gtk.Label(label=self.translated)
            result.set_css_classes(["result"])
            result.set_wrap(True)
            result.set_xalign(0)
            result.set_max_width_chars(55)
            box.append(result)

            btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            btn_bar.set_css_classes(["button-bar"])
            btn_bar.set_halign(Gtk.Align.END)

            copy_btn = Gtk.Button(label=BTN_COPY)
            copy_btn.set_css_classes(["action-btn", "copy"])
            copy_btn.connect("clicked", self._on_copy)
            btn_bar.append(copy_btn)
            box.append(btn_bar)
        else:
            self._loading_label = Gtk.Label(label=TRANSLATING)
            self._loading_label.set_css_classes(["hint"])
            self._loading_label.set_wrap(True)
            self._loading_label.set_xalign(0)
            box.append(self._loading_label)

        self.content_area.append(box)

    def _show_edit_mode(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_has_frame(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(60)
        scrolled.set_max_content_height(150)
        scrolled.set_propagate_natural_height(True)

        self._edit_view = Gtk.TextView()
        self._edit_view.get_buffer().set_text(self.text)
        self._edit_view.set_css_classes(["orig-edit"])
        self._edit_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scrolled.set_child(self._edit_view)
        box.append(scrolled)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_bar.set_css_classes(["button-bar"])
        btn_bar.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=BTN_CANCEL)
        cancel_btn.set_css_classes(["action-btn"])
        cancel_btn.connect("clicked", self._on_edit_cancel)
        btn_bar.append(cancel_btn)

        retrans_btn = Gtk.Button(label=BTN_RETRANSLATE)
        retrans_btn.set_css_classes(["action-btn", "primary"])
        retrans_btn.connect("clicked", self._on_retranslate)
        btn_bar.append(retrans_btn)

        box.append(btn_bar)
        self.content_area.append(box)
        self._edit_view.grab_focus()

    def _show_explain_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])

        if self.explanation:
            body = Gtk.Label(label=self.explanation)
            body.set_css_classes(["explain-body"])
            body.set_wrap(True)
            body.set_xalign(0)
            body.set_max_width_chars(55)
            box.append(body)
        else:
            self._loading_label = Gtk.Label(label=EXPLAINING)
            self._loading_label.set_css_classes(["hint"])
            self._loading_label.set_wrap(True)
            self._loading_label.set_xalign(0)
            box.append(self._loading_label)

        self.content_area.append(box)

    def _show_chat_tab(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._chat_scroll = Gtk.ScrolledWindow()
        self._chat_scroll.set_has_frame(False)
        self._chat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._chat_scroll.set_propagate_natural_height(True)
        self._chat_scroll.set_min_content_height(60)
        self._chat_scroll.set_max_content_height(400)

        self._chat_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._chat_list.set_css_classes(["chat-area"])
        self._chat_scroll.set_child(self._chat_list)

        for msg in self.chat_messages:
            self._append_chat_bubble(msg["role"], msg["content"])

        vbox.append(self._chat_scroll)

        input_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_bar.set_css_classes(["chat-input-bar"])

        self._chat_input = Gtk.Entry()
        self._chat_input.set_css_classes(["chat-input"])
        self._chat_input.set_hexpand(True)
        self._chat_input.set_placeholder_text(CHAT_PLACEHOLDER)
        self._chat_input.connect("activate", self._on_chat_send)
        input_bar.append(self._chat_input)

        self._chat_send_btn = Gtk.Button(label=BTN_SEND)
        self._chat_send_btn.set_css_classes(["chat-send"])
        self._chat_send_btn.connect("clicked", self._on_chat_send)
        input_bar.append(self._chat_send_btn)

        vbox.append(input_bar)
        self.content_area.append(vbox)
        self._chat_input.grab_focus()

    def _append_chat_bubble(self, role, text):
        label = Gtk.Label(label=text)
        label.set_wrap(True)
        label.set_max_width_chars(45)
        label.set_xalign(0)

        align = Gtk.Box()
        if role == "user":
            label.set_css_classes(["chat-bubble-user"])
            align.set_halign(Gtk.Align.END)
        else:
            label.set_css_classes(["chat-bubble-ai"])
            align.set_halign(Gtk.Align.START)

        align.append(label)
        self._chat_list.append(align)

    def set_translation(self, translated):
        self.translated = translated
        if self._current_tab == "translate" and not self._editing:
            self._clear_content()
            self._show_translate_tab()
            self._resize_to_content()

    def set_explanation(self, explanation):
        self.explanation = explanation
        if self._current_tab == "explain":
            self._clear_content()
            self._show_explain_tab()
            self._resize_to_content()

    def show_loading(self):
        pass

    def _on_edit(self, btn):
        self._editing = True
        if self._current_tab == "translate":
            self._clear_content()
            self._show_translate_tab()

    def _on_edit_cancel(self, btn):
        self._editing = False
        if self._current_tab == "translate":
            self._clear_content()
            self._show_translate_tab()

    def _on_retranslate(self, btn):
        buf = self._edit_view.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        new_text = buf.get_text(start, end, False).strip()
        if not new_text:
            return

        self.text = new_text
        self._editing = False
        self.translated = ""
        self._clear_content()
        self._show_translate_tab()
        self._resize_to_content()

        def worker():
            result = translate(self.text, self.config, self.history_db)
            GLib.idle_add(self._on_translate_done, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_translate_done(self, result):
        self.set_translation(result)
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

    def _on_chat_send(self, widget):
        if isinstance(widget, Gtk.Button):
            text = self._chat_input.get_text().strip()
        else:
            text = widget.get_text().strip()

        if not text:
            return

        self._chat_input.set_text("")
        self.chat_messages.append({"role": "user", "content": text})
        self._append_chat_bubble("user", text)

        self._chat_send_btn.set_sensitive(False)
        thinking = Gtk.Label(label=CHAT_THINKING)
        thinking.set_css_classes(["chat-bubble-ai"])
        thinking.set_wrap(True)
        thinking.set_xalign(0)
        thinking_align = Gtk.Box()
        thinking_align.set_halign(Gtk.Align.START)
        thinking_align.append(thinking)
        self._chat_list.append(thinking_align)

        def worker():
            result = do_chat(
                self.text, self.translated, self.explanation,
                self.chat_messages[:-1], text, self.config,
            )
            GLib.idle_add(self._on_chat_done, result, thinking_align)

        threading.Thread(target=worker, daemon=True).start()

    def _on_chat_done(self, result, thinking_widget):
        self._chat_list.remove(thinking_widget)
        self.chat_messages.append({"role": "assistant", "content": result})
        self._append_chat_bubble("assistant", result)
        self._chat_send_btn.set_sensitive(True)
        return False

    def _resize_to_content(self):
        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        max_h = 900
        if monitors.get_n_items() > 0:
            m = monitors.get_item(0)
            geo = m.get_geometry()
            max_h = int(geo.height * 0.5)
        self.set_default_size(480, -1)

    def _truncate(self, text):
        max_chars = 300
        return text if len(text) <= max_chars else text[:max_chars] + "..."

    def _on_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        focused = self.get_focus()
        if isinstance(focused, (Gtk.Entry, Gtk.TextView)):
            return False

        if keyval == Gdk.KEY_s:
            self._switch_tab("translate")
            return True
        elif keyval == Gdk.KEY_w:
            self._switch_tab("explain")
            return True
        elif keyval == Gdk.KEY_c:
            self._switch_tab("chat")
            return True
        elif keyval == Gdk.KEY_e:
            self._on_edit(self.edit_btn)
            return True

        return False
