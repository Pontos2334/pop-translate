import subprocess
import os
import re
import threading
from urllib.parse import quote_plus, urlparse

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from ..css import CSS
from ..i18n import (
    APP_TITLE, TRANSLATING, EXPLAINING, OCR_LOADING,
    BTN_COPY, BTN_COPIED, BTN_COPY_ORIGINAL, BTN_COPIED_ORIG,
    BTN_EDIT, BTN_RETRANSLATE, BTN_REEXPLAIN, BTN_DETAILED_EXPLAIN, BTN_CANCEL, BTN_SEND,
    BTN_SEARCH, BTN_SCREENSHOT, BTN_THINKING, BTN_WITH_CONTEXT, BTN_NO_CONTEXT,
    TAB_TRANSLATE, TAB_EXPLAIN, TAB_CHAT,
    SHORTCUT_HINT, CHAT_PLACEHOLDER, CHAT_THINKING,
)
from ..translate import translate_stream, explain_stream, chat_stream, is_code_or_error
from ..clipboard import copy_text

BUILTIN_MODELS = ("deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro")
WINDOW_WIDTH = 640
BARE_DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}([/?#].*)?$")


class TranslateWindow(Gtk.ApplicationWindow):
    def __init__(self, app, text, config, history_db, default_tab="translate", ocr_bootstrapping=False):
        super().__init__(application=app, title="translate")
        self.original_text = text
        self.text = text
        self.translated = ""
        self.explanation = ""
        self.chat_messages = []
        self.config = config
        self.history_db = history_db
        self._loading_label = None
        self._translate_loading_label = None
        self._explain_loading_label = None
        self._translate_result_view = None
        self._translate_copy_btn = None
        self._explain_result_view = None
        self._explain_controls = None
        self._chat_stream_view = None
        self._chat_stream_text = ""
        self._readonly_text_min_heights = {}
        self._content_scroll = None
        self._resize_timeout_id = None
        self._default_tab = default_tab
        self._editing = False
        self._translate_loading = False
        self._explain_loading = False
        self._chat_loading = False
        self._translate_request_text = None
        self._explain_request_text = None
        self._chat_request_text = None
        self._translate_request_model = None
        self._explain_request_model = None
        self._chat_request_model = None
        self._translate_request_thinking = False
        self._explain_request_thinking = False
        self._chat_request_thinking = False
        self._chat_request_include_context = True
        self._translate_cancel_event = None
        self._explain_cancel_event = None
        self._chat_cancel_event = None
        self._max_content_height = 420
        self._translate_model = self._initial_model()
        self._explain_model = self._initial_model()
        self._chat_model = self._initial_model()
        self._translate_thinking = False
        self._explain_thinking = False
        self._explain_detailed = False
        self._chat_thinking = False
        self._chat_include_context = True
        self._autoclose_timeout_id = None
        self._ocr_bootstrapping = ocr_bootstrapping
        self._model_choices = self._build_model_choices()

        self.set_decorated(False)
        self.set_resizable(True)
        self.set_default_size(WINDOW_WIDTH, 320)

        self._load_css()
        self._build_ui()
        self._switch_tab(default_tab)

        self.connect("close-request", self._on_close)
        self.connect("realize", self._on_realize)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Auto-Close: Reset timer on keyboard input (using CAPTURE phase to see all keystrokes)
        key_capture_ctrl = Gtk.EventControllerKey.new()
        key_capture_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_capture_ctrl.connect("key-pressed", lambda ctrl, kv, kc, st: self._reset_autoclose_timer())
        self.add_controller(key_capture_ctrl)

        # Auto-Close: Reset timer on mouse entering window
        motion_ctrl = Gtk.EventControllerMotion.new()
        motion_ctrl.connect("enter", self._reset_autoclose_timer)
        self.add_controller(motion_ctrl)

        # Auto-Close: Reset timer on click
        click_ctrl = Gtk.GestureClick.new()
        click_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_ctrl.connect("pressed", self._reset_autoclose_timer_click)
        self.add_controller(click_ctrl)

        # Start initial autoclose timer
        self._start_autoclose_timer()

    def _on_close(self, _window):
        self._cancel_active_requests()
        self._stop_autoclose_timer()
        if self._resize_timeout_id:
            GLib.source_remove(self._resize_timeout_id)
            self._resize_timeout_id = None
        self.get_application().quit()
        return False

    def _cancel_translation_request(self):
        if self._translate_cancel_event is not None:
            self._translate_cancel_event.set()
        self._translate_cancel_event = None
        self._translate_loading = False
        self._translate_request_text = None
        self._translate_request_model = None
        self._translate_request_thinking = False

    def _cancel_explain_request(self):
        if self._explain_cancel_event is not None:
            self._explain_cancel_event.set()
        self._explain_cancel_event = None
        self._explain_loading = False
        self._explain_request_text = None
        self._explain_request_model = None
        self._explain_request_thinking = False

    def _cancel_chat_request(self):
        if self._chat_cancel_event is not None:
            self._chat_cancel_event.set()
        self._chat_cancel_event = None
        self._chat_loading = False
        self._chat_request_text = None
        self._chat_request_model = None
        self._chat_request_thinking = False
        self._chat_request_include_context = True

    def _cancel_active_requests(self):
        self._cancel_translation_request()
        self._cancel_explain_request()
        self._cancel_chat_request()

    def _start_autoclose_timer(self):
        self._stop_autoclose_timer()
        self._autoclose_timeout_id = GLib.timeout_add_seconds(
            180, self._on_autoclose_timeout
        )

    def _stop_autoclose_timer(self):
        if hasattr(self, "_autoclose_timeout_id") and self._autoclose_timeout_id:
            GLib.source_remove(self._autoclose_timeout_id)
            self._autoclose_timeout_id = None

    def _reset_autoclose_timer(self, *args):
        self._start_autoclose_timer()
        return False

    def _reset_autoclose_timer_click(self, gesture, n_press, x, y):
        self._start_autoclose_timer()
        return False

    def _on_autoclose_timeout(self):
        self._autoclose_timeout_id = None
        self.close()
        return False

    def _on_realize(self, widget):
        GLib.idle_add(self._focus_window)
        if hasattr(self, "_ocr_bootstrapping") and self._ocr_bootstrapping:
            self._start_ocr_bootstrap_worker()

    def _start_ocr_bootstrap_worker(self):
        def worker():
            from ..__main__ import ocr_image
            text = ocr_image()
            GLib.idle_add(self._on_screenshot_done, text)
        threading.Thread(target=worker, daemon=True).start()

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
        self.outer.set_focusable(True)
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

        search_btn = Gtk.Button(label=BTN_SEARCH)
        search_btn.set_css_classes(["title-btn"])
        search_btn.connect("clicked", self._on_search)
        title_bar.append(search_btn)

        ocr_btn = Gtk.Button(label=BTN_SCREENSHOT)
        ocr_btn.set_css_classes(["title-btn"])
        ocr_btn.connect("clicked", self._on_screenshot_ocr)
        title_bar.append(ocr_btn)

        self.copy_orig_btn = Gtk.Button(label=BTN_COPY_ORIGINAL)
        self.copy_orig_btn.set_css_classes(["title-btn"])
        self.copy_orig_btn.connect("clicked", self._on_copy_original)
        title_bar.append(self.copy_orig_btn)

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

    def _on_screenshot_ocr(self, button):
        self.hide()
        # Defer screen capture slightly to ensure window has vanished from screen
        GLib.timeout_add(250, self._start_screenshot_worker)

    def _start_screenshot_worker(self):
        def worker():
            from ..__main__ import capture_screenshot, ocr_image
            success = capture_screenshot()
            if success:
                GLib.idle_add(self._on_screenshot_captured)
                text = ocr_image()
                GLib.idle_add(self._on_screenshot_done, text)
            else:
                GLib.idle_add(self.show)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _on_screenshot_captured(self):
        self._ocr_bootstrapping = True
        self._reset_autoclose_timer()
        self.show()
        self._switch_tab(self._current_tab)

    def _on_screenshot_done(self, text):
        self._ocr_bootstrapping = False
        self._reset_autoclose_timer()
        self.show()
        self._cancel_active_requests()
        if not text:
            # Show empty translate tab if no text was captured
            self.original_text = ""
            self.text = ""
            self.translated = ""
            self.explanation = ""
            self.chat_messages = []
            self._chat_stream_text = ""
            self._switch_tab("translate")
            return
            
        self.original_text = text
        self.text = text
        self.translated = ""
        self.explanation = ""
        self.chat_messages = []
        self._chat_stream_text = ""
        threading.Thread(target=copy_text, args=(text,), daemon=True).start()
        
        if is_code_or_error(text):
            self._switch_tab("explain")
        else:
            from ..translate import should_translate
            tab_id = "translate" if should_translate(text) else "explain"
            self._switch_tab(tab_id)

    def _show_ocr_loading_state(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])
        self._loading_label = Gtk.Label(label=OCR_LOADING)
        self._loading_label.set_css_classes(["hint"])
        self._loading_label.set_wrap(True)
        self._loading_label.set_xalign(0)
        box.append(self._loading_label)
        self.content_area.append(self._wrap_scroll(box))

    def _on_copy_original(self, btn):
        text = self.text
        if not text or text == OCR_LOADING:
            return

        btn.set_label(BTN_COPIED_ORIG)
        btn.set_sensitive(False)

        def worker():
            copy_text(text)

            def reset_btn():
                btn.set_label(BTN_COPY_ORIGINAL)
                btn.set_sensitive(True)
                return False
            GLib.timeout_add_seconds(1, reset_btn)

        threading.Thread(target=worker, daemon=True).start()

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
        hint.set_hexpand(True)
        hint.set_ellipsize(Pango.EllipsizeMode.END)
        bar.append(hint)
        self.outer.append(bar)

    def _clear_content(self):
        while True:
            child = self.content_area.get_first_child()
            if child is None:
                break
            self.content_area.remove(child)
        self._loading_label = None
        self._translate_loading_label = None
        self._explain_loading_label = None
        self._translate_result_view = None
        self._translate_copy_btn = None
        self._explain_result_view = None
        self._explain_controls = None
        self._chat_stream_view = None
        self._readonly_text_min_heights = {}
        self._content_scroll = None

    def _switch_tab(self, tab_id):
        self._current_tab = tab_id
        for tid, btn in self.tab_btns.items():
            if tid == tab_id:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

        self._clear_content()

        if hasattr(self, "_ocr_bootstrapping") and self._ocr_bootstrapping:
            self._show_ocr_loading_state()
            self._resize_to_content()
            return

        if tab_id == "translate":
            self._show_translate_tab()
            if not self.translated and not self._editing:
                self._ensure_translation()
        elif tab_id == "explain":
            self._show_explain_tab()
            if not self.explanation:
                self._ensure_explanation()
        elif tab_id == "chat":
            self._show_chat_tab()

        self._resize_to_content()

    def _ensure_translation(self):
        if self._translate_loading or self.translated:
            return
        self._start_translation(self._api_model(self._translate_model), False, True)

    def _start_translation(self, model, thinking_enabled, use_cache):
        self._cancel_translation_request()
        text = self.text
        cancel_event = threading.Event()
        self._translate_loading = True
        self._translate_request_text = text
        self._translate_request_model = model
        self._translate_request_thinking = thinking_enabled
        self._translate_cancel_event = cancel_event

        def worker():
            chunks = []
            for chunk in translate_stream(
                text,
                self.config,
                self.history_db,
                model=model,
                thinking_enabled=thinking_enabled,
                use_cache=use_cache,
                cancel_event=cancel_event,
            ):
                if cancel_event.is_set():
                    return
                chunks.append(chunk)
                GLib.idle_add(self._on_translate_chunk, text, model, thinking_enabled, cancel_event, chunk)
            result = "".join(chunks).strip()
            GLib.idle_add(self._on_translate_done, text, model, thinking_enabled, cancel_event, result)

        threading.Thread(target=worker, daemon=True).start()

    def _initial_model(self):
        return self.config.model

    def _selected_model(self, dropdown):
        index = dropdown.get_selected()
        if index >= len(self._model_choices):
            return self.config.model
        return self._model_choices[index]

    def _select_model(self, dropdown, model):
        try:
            index = self._model_choices.index(model)
        except ValueError:
            index = 0
        dropdown.set_selected(index)

    def _build_model_choices(self):
        choices = []
        for name in (self.config.model, *BUILTIN_MODELS):
            if name and name not in choices:
                choices.append(name)
        return tuple(choices)

    def _api_model(self, selected_model):
        return None if selected_model == self.config.model else selected_model

    def _display_model(self, api_model):
        return api_model or self.config.model

    def _build_model_controls(
        self,
        current_model,
        thinking_enabled,
        on_regenerate,
        regen_label,
        on_model_changed=None,
        on_thinking_changed=None,
    ):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_css_classes(["control-bar"])
        bar.set_halign(Gtk.Align.END)

        model_dropdown = Gtk.DropDown.new_from_strings(list(self._model_choices))
        model_dropdown.set_css_classes(["model-select"])
        self._select_model(model_dropdown, current_model)
        if on_model_changed:
            model_dropdown.connect("notify::selected", on_model_changed)
        bar.append(model_dropdown)

        thinking_check = Gtk.CheckButton(label=BTN_THINKING)
        thinking_check.set_css_classes(["thinking-toggle"])
        thinking_check.set_active(thinking_enabled)
        if on_thinking_changed:
            thinking_check.connect("toggled", on_thinking_changed)
        bar.append(thinking_check)

        regen_btn = Gtk.Button(label=regen_label)
        regen_btn.set_css_classes(["action-btn", "primary"])
        regen_btn.connect("clicked", on_regenerate, model_dropdown, thinking_check)
        bar.append(regen_btn)

        return bar

    def _append_original(self, box):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_css_classes(["orig-card"])

        orig = self._readonly_text_view(self._truncate(self.text), ["orig"], min_height=28)
        
        card.append(orig)
        box.append(card)


    def _ensure_explanation(self):
        if self._explain_loading or self.explanation:
            return
        self._start_explanation(self._api_model(self._explain_model), False)

    def _start_explanation(self, model, thinking_enabled, detailed=False):
        self._cancel_explain_request()
        text = self.text
        cancel_event = threading.Event()
        self._explain_loading = True
        self._explain_request_text = text
        self._explain_request_model = model
        self._explain_request_thinking = thinking_enabled
        self._explain_detailed = detailed
        self._explain_cancel_event = cancel_event

        def worker():
            chunks = []
            for chunk in explain_stream(
                text,
                self.config,
                model=model,
                thinking_enabled=thinking_enabled,
                detailed=detailed,
                cancel_event=cancel_event,
            ):
                if cancel_event.is_set():
                    return
                chunks.append(chunk)
                GLib.idle_add(self._on_explain_chunk, text, model, thinking_enabled, cancel_event, chunk)
            result = "".join(chunks).strip()
            GLib.idle_add(self._on_explain_done, text, model, thinking_enabled, cancel_event, result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_translate_tab(self):
        if self._editing:
            self._show_edit_mode(BTN_RETRANSLATE, self._on_retranslate)
            return

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])
        self._append_original(box)

        if not self.translated:
            self._translate_loading_label = Gtk.Label(label=TRANSLATING)
            self._translate_loading_label.set_css_classes(["hint"])
            self._translate_loading_label.set_wrap(True)
            self._translate_loading_label.set_xalign(0)
            box.append(self._translate_loading_label)

        self._translate_result_view = self._readonly_text_view(self.translated, ["result"], min_height=28)
        box.append(self._translate_result_view)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_bar.set_css_classes(["button-bar"])
        btn_bar.set_halign(Gtk.Align.END)

        self._translate_copy_btn = Gtk.Button(label=BTN_COPY)
        self._translate_copy_btn.set_css_classes(["action-btn", "copy"])
        self._translate_copy_btn.set_sensitive(bool(self.translated) and not self._translate_loading)
        self._translate_copy_btn.connect("clicked", self._on_copy)
        btn_bar.append(self._translate_copy_btn)
        box.append(btn_bar)

        box.append(self._build_model_controls(
            self._translate_model,
            self._translate_thinking,
            self._on_translate_regenerate,
            BTN_RETRANSLATE,
        ))
        self.content_area.append(self._wrap_scroll(box))

    def _show_edit_mode(self, primary_label, on_primary):
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
        edit_key_ctrl = Gtk.EventControllerKey.new()
        edit_key_ctrl.connect("key-pressed", self._on_edit_key)
        self._edit_view.add_controller(edit_key_ctrl)
        scrolled.set_child(self._edit_view)
        box.append(scrolled)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_bar.set_css_classes(["button-bar"])
        btn_bar.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=BTN_CANCEL)
        cancel_btn.set_css_classes(["action-btn"])
        cancel_btn.connect("clicked", self._on_edit_cancel)
        btn_bar.append(cancel_btn)

        primary_btn = Gtk.Button(label=primary_label)
        primary_btn.set_css_classes(["action-btn", "primary"])
        primary_btn.connect("clicked", on_primary)
        btn_bar.append(primary_btn)

        box.append(btn_bar)
        self.content_area.append(self._wrap_scroll(box))
        self._edit_view.grab_focus()

    def _show_explain_tab(self):
        if self._editing:
            self._show_edit_mode(BTN_REEXPLAIN, self._on_reexplain)
            return

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])
        self._append_original(box)

        if not self.explanation:
            self._explain_loading_label = Gtk.Label(label=EXPLAINING)
            self._explain_loading_label.set_css_classes(["hint"])
            self._explain_loading_label.set_wrap(True)
            self._explain_loading_label.set_xalign(0)
            box.append(self._explain_loading_label)

        self._explain_result_view = self._readonly_text_view(self.explanation, ["explain-body"], min_height=28, markdown=True)
        box.append(self._explain_result_view)

        controls = self._build_model_controls(
            self._explain_model,
            self._explain_thinking,
            self._on_explain_regenerate,
            BTN_REEXPLAIN,
        )
        self._explain_controls = controls
        if self.explanation and not self._explain_detailed:
            self._append_detail_button()
        box.append(controls)
        self.content_area.append(self._wrap_scroll(box))

    def _show_chat_tab(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.set_css_classes(["control-bar", "chat-control-bar"])

        self._chat_model_dropdown = Gtk.DropDown.new_from_strings(list(self._model_choices))
        self._chat_model_dropdown.set_css_classes(["model-select"])
        self._select_model(self._chat_model_dropdown, self._chat_model)
        self._chat_model_dropdown.connect("notify::selected", self._on_chat_model_changed)
        controls.append(self._chat_model_dropdown)

        self._chat_thinking_check = Gtk.CheckButton(label=BTN_THINKING)
        self._chat_thinking_check.set_css_classes(["thinking-toggle"])
        self._chat_thinking_check.set_active(self._chat_thinking)
        self._chat_thinking_check.connect("toggled", self._on_chat_thinking_toggled)
        controls.append(self._chat_thinking_check)

        self._chat_context_btn = Gtk.Button(label=BTN_WITH_CONTEXT if self._chat_include_context else BTN_NO_CONTEXT)
        self._chat_context_btn.set_css_classes(["action-btn"])
        self._chat_context_btn.connect("clicked", self._on_chat_context_toggle)
        controls.append(self._chat_context_btn)

        vbox.append(controls)

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

        if self._chat_loading:
            bubble_text = self._chat_stream_text or CHAT_THINKING
            self._chat_stream_view, _align = self._append_chat_bubble("assistant", bubble_text)

        vbox.append(self._chat_scroll)

        input_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_bar.set_css_classes(["chat-input-bar"])

        scrolled_input = Gtk.ScrolledWindow()
        scrolled_input.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_input.set_min_content_height(36)
        scrolled_input.set_max_content_height(100)
        scrolled_input.set_propagate_natural_height(True)
        scrolled_input.set_hexpand(True)
        scrolled_input.set_focusable(False)

        self._chat_input = Gtk.TextView()
        self._chat_input.set_css_classes(["chat-input-view"])
        self._chat_input.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._chat_input.set_accepts_tab(False)

        chat_key_ctrl = Gtk.EventControllerKey.new()
        chat_key_ctrl.connect("key-pressed", self._on_chat_input_key)
        self._chat_input.add_controller(chat_key_ctrl)

        self._chat_input.get_buffer().connect("changed", self._on_chat_input_changed)

        scrolled_input.set_child(self._chat_input)
        input_bar.append(scrolled_input)

        self._chat_send_btn = Gtk.Button(label=BTN_SEND)
        self._chat_send_btn.set_css_classes(["chat-send"])
        self._chat_send_btn.set_sensitive(not self._chat_loading)
        self._chat_send_btn.connect("clicked", self._on_chat_send)
        input_bar.append(self._chat_send_btn)

        vbox.append(input_bar)
        self.content_area.append(vbox)
        self._chat_input.grab_focus()


    def _on_chat_model_changed(self, dropdown, param):
        self._chat_model = self._selected_model(dropdown)
        self._cancel_chat_if_loading()

    def _on_chat_thinking_toggled(self, check):
        self._chat_thinking = check.get_active()
        self._cancel_chat_if_loading()

    def _on_chat_context_toggle(self, btn):
        self._chat_include_context = not self._chat_include_context
        if self._cancel_chat_if_loading():
            return
        btn.set_label(BTN_WITH_CONTEXT if self._chat_include_context else BTN_NO_CONTEXT)

    def _toggle_chat_context(self):
        self._chat_include_context = not self._chat_include_context
        self._cancel_chat_if_loading()
        if self._current_tab == "chat":
            self._clear_content()
            self._show_chat_tab()
            self._resize_to_content()

    def _cancel_chat_if_loading(self):
        if not self._chat_loading:
            return False
        self._cancel_chat_request()
        if self._current_tab == "chat":
            self._clear_content()
            self._show_chat_tab()
            self._resize_to_content()
        return True

    def _wrap_scroll(self, child):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_has_frame(False)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_min_content_height(40)
        self._max_content_height = self._content_height_limit()
        scrolled.set_max_content_height(self._max_content_height)
        scrolled.set_child(child)
        self._content_scroll = scrolled
        return scrolled

    def _readonly_text_view(self, text, css_classes, min_height=24, markdown=False):
        view = Gtk.TextView()
        view.set_css_classes(css_classes)
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_accepts_tab(False)
        view.set_hexpand(True)
        view.set_vexpand(False)
        view.set_valign(Gtk.Align.START)
        self._readonly_text_min_heights[view] = min_height
        view.get_buffer().connect("changed", lambda _buf, v=view: self._schedule_text_view_height(v))
        if markdown:
            self._set_text_view_markdown(view, text or "")
        else:
            view.get_buffer().set_text(text or "")
        self._schedule_text_view_height(view)
        return view

    def _ensure_markdown_tags(self, buf):
        table = buf.get_tag_table()
        if table.lookup("md_bold") is None:
            buf.create_tag("md_bold", weight=Pango.Weight.BOLD)
        if table.lookup("md_italic") is None:
            buf.create_tag("md_italic", style=Pango.Style.ITALIC)
        if table.lookup("md_code") is None:
            buf.create_tag(
                "md_code",
                family="monospace",
                background="#f4f4f5",
                foreground="#18181b",
            )
        if table.lookup("md_heading") is None:
            buf.create_tag("md_heading", weight=Pango.Weight.BOLD, scale=1.18)
        if table.lookup("md_link") is None:
            buf.create_tag("md_link", underline=Pango.Underline.SINGLE, foreground="#0969da")

    def _insert_tagged(self, buf, text, tag_names=()):
        if not text:
            return
        start_offset = buf.get_end_iter().get_offset()
        buf.insert(buf.get_end_iter(), text)
        start = buf.get_iter_at_offset(start_offset)
        end = buf.get_iter_at_offset(start_offset + len(text))
        for tag_name in tag_names:
            buf.apply_tag_by_name(tag_name, start, end)

    def _insert_markdown_inline(self, buf, text, base_tags=()):
        pattern = re.compile(
            r"`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\([^)]+\)|(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)"
        )
        pos = 0
        for match in pattern.finditer(text):
            if match.start() > pos:
                self._insert_tagged(buf, text[pos:match.start()], base_tags)
            if match.group(1) is not None:
                self._insert_tagged(buf, match.group(1), (*base_tags, "md_code"))
            elif match.group(2) is not None:
                self._insert_tagged(buf, match.group(2), (*base_tags, "md_bold"))
            elif match.group(3) is not None:
                self._insert_tagged(buf, match.group(3), (*base_tags, "md_link"))
            elif match.group(4) is not None:
                self._insert_tagged(buf, match.group(4), (*base_tags, "md_italic"))
            pos = match.end()
        if pos < len(text):
            self._insert_tagged(buf, text[pos:], base_tags)

    def _set_text_view_markdown(self, view, text):
        if view is None:
            return
        buf = view.get_buffer()
        self._ensure_markdown_tags(buf)
        buf.set_text("")
        if not text:
            self._schedule_text_view_height(view)
            return

        in_code_block = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                self._insert_tagged(buf, line + "\n", ("md_code",))
                continue

            heading = re.match(r"^\s*#{1,4}\s+(.+)$", line)
            bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
            numbered = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
            if heading:
                self._insert_markdown_inline(buf, heading.group(1).strip(), ("md_heading",))
            elif bullet:
                self._insert_tagged(buf, "  • ")
                self._insert_markdown_inline(buf, bullet.group(1))
            elif numbered:
                self._insert_tagged(buf, f"  {numbered.group(1)}. ")
                self._insert_markdown_inline(buf, numbered.group(2))
            else:
                self._insert_markdown_inline(buf, line)
            self._insert_tagged(buf, "\n")

        self._schedule_text_view_height(view)

    def _schedule_text_view_height(self, view):
        GLib.idle_add(self._refresh_text_view_height, view)

    def _refresh_text_view_height(self, view, request_resize=True):
        if view is None or view.get_parent() is None:
            return False
        if view.get_allocated_width() <= 1:
            if request_resize:
                GLib.timeout_add(20, self._refresh_text_view_height, view)
            return False
        min_height = self._readonly_text_min_heights.get(view, 24)
        buf = view.get_buffer()
        end = buf.get_end_iter()
        rect = view.get_iter_location(end)
        height = max(min_height, rect.y + rect.height + 6)
        view.set_size_request(-1, height)
        if request_resize:
            self._resize_to_content()
        return False

    def _refresh_visible_text_heights(self):
        for view in list(self._readonly_text_min_heights):
            self._refresh_text_view_height(view, request_resize=False)

    def _set_text_view_text(self, view, text):
        if view is None:
            return
        view.get_buffer().set_text(text or "")
        self._schedule_text_view_height(view)

    def _append_text_view_text(self, view, text):
        if view is None or not text:
            return
        buf = view.get_buffer()
        end = buf.get_end_iter()
        buf.insert(end, text)
        self._schedule_text_view_height(view)

    def _remove_label(self, label):
        if label is None:
            return
        parent = label.get_parent()
        if parent is not None:
            parent.remove(label)

    def _remove_translate_loading_label(self):
        self._remove_label(self._translate_loading_label)
        self._translate_loading_label = None

    def _remove_explain_loading_label(self):
        self._remove_label(self._explain_loading_label)
        self._explain_loading_label = None

    def _append_detail_button(self):
        if self._explain_controls is None or self._explain_detailed:
            return
        detail_btn = Gtk.Button(label=BTN_DETAILED_EXPLAIN)
        detail_btn.set_css_classes(["action-btn", "primary"])
        detail_btn.connect("clicked", self._on_detailed_explain)
        self._explain_controls.append(detail_btn)

    def _append_chat_bubble(self, role, text):
        css_classes = ["chat-bubble-user"] if role == "user" else ["chat-bubble-ai"]
        view = self._readonly_text_view(text, css_classes, min_height=40, markdown=(role != "user"))
        if role == "user":
            view.set_justification(Gtk.Justification.LEFT)
        else:
            view.set_justification(Gtk.Justification.LEFT)

        align = Gtk.Box()
        if role == "user":
            align.set_halign(Gtk.Align.END)
        else:
            align.set_halign(Gtk.Align.START)

        align.append(view)
        self._chat_list.append(align)
        self._scroll_chat_to_bottom()
        return view, align

    def _scroll_chat_to_bottom(self):
        if not hasattr(self, "_chat_scroll") or self._chat_scroll is None:
            return

        def scroll():
            adj = self._chat_scroll.get_vadjustment()
            adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))
            return False

        GLib.idle_add(scroll)

    def set_translation(self, translated):
        self.translated = translated
        if self._current_tab == "translate" and not self._editing:
            self._set_text_view_text(self._translate_result_view, translated)
            if self._translate_copy_btn is not None:
                self._translate_copy_btn.set_sensitive(bool(translated))
            self._resize_to_content()

    def set_explanation(self, explanation):
        self.explanation = explanation
        if self._current_tab == "explain":
            self._set_text_view_markdown(self._explain_result_view, explanation)
            self._resize_to_content()

    def _is_translate_request_current(self, text, model, thinking_enabled, cancel_event):
        return (
            cancel_event is not None
            and not cancel_event.is_set()
            and self._translate_cancel_event is cancel_event
            and text == self.text
            and self._translate_model == self._display_model(model)
            and self._translate_thinking == thinking_enabled
            and self._translate_request_text == text
            and self._translate_request_model == model
            and self._translate_request_thinking == thinking_enabled
        )

    def _is_explain_request_current(self, text, model, thinking_enabled, cancel_event):
        return (
            cancel_event is not None
            and not cancel_event.is_set()
            and self._explain_cancel_event is cancel_event
            and text == self.text
            and self._explain_model == self._display_model(model)
            and self._explain_thinking == thinking_enabled
            and self._explain_request_text == text
            and self._explain_request_model == model
            and self._explain_request_thinking == thinking_enabled
        )

    def _on_translate_chunk(self, text, model, thinking_enabled, cancel_event, chunk):
        if not self._is_translate_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if not chunk:
            return False
        self.translated += chunk
        if self._current_tab == "translate" and not self._editing:
            self._remove_translate_loading_label()
            self._append_text_view_text(self._translate_result_view, chunk)
            self._resize_to_content()
        return False

    def _on_explain_chunk(self, text, model, thinking_enabled, cancel_event, chunk):
        if not self._is_explain_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if not chunk:
            return False
        self.explanation += chunk
        if self._current_tab == "explain":
            self._remove_explain_loading_label()
            self._append_text_view_text(self._explain_result_view, chunk)
            self._resize_to_content()
        return False

    def _on_translate_done(self, text, model, thinking_enabled, cancel_event, result):
        if (
            self._translate_cancel_event is cancel_event
            and self._translate_request_text == text
            and self._translate_request_model == model
            and self._translate_request_thinking == thinking_enabled
        ):
            self._translate_loading = False
            self._translate_request_text = None
            self._translate_request_model = None
            self._translate_request_thinking = False
            self._translate_cancel_event = None
        if (
            cancel_event.is_set()
            or text != self.text
            or self._translate_model != self._display_model(model)
            or self._translate_thinking != thinking_enabled
        ):
            return False
        if self._current_tab == "translate" and not self._editing:
            self._remove_translate_loading_label()
        self.set_translation(result)
        return False

    def _on_explain_done(self, text, model, thinking_enabled, cancel_event, result):
        if (
            self._explain_cancel_event is cancel_event
            and self._explain_request_text == text
            and self._explain_request_model == model
            and self._explain_request_thinking == thinking_enabled
        ):
            self._explain_loading = False
            self._explain_request_text = None
            self._explain_request_model = None
            self._explain_request_thinking = False
            self._explain_cancel_event = None
        if (
            cancel_event.is_set()
            or text != self.text
            or self._explain_model != self._display_model(model)
            or self._explain_thinking != thinking_enabled
        ):
            return False
        if self._current_tab == "explain":
            self._remove_explain_loading_label()
        self.set_explanation(result)
        if self._current_tab == "explain" and self.explanation and not self._explain_detailed:
            self._append_detail_button()
        return False

    def show_loading(self):
        pass

    def _on_edit(self, btn):
        self._editing = True
        self._clear_content()
        if self._current_tab == "translate":
            self._show_translate_tab()
        elif self._current_tab == "explain":
            self._show_explain_tab()
        self._resize_to_content()

    def _on_edit_cancel(self, btn):
        self._editing = False
        self._clear_content()
        if self._current_tab == "translate":
            self._show_translate_tab()
        elif self._current_tab == "explain":
            self._show_explain_tab()
        self._resize_to_content()

    def _on_edit_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self._on_edit_cancel(self.edit_btn)
            return True
        return False

    def _on_translate_regenerate(self, btn, model_dropdown, thinking_check):
        self._translate_model = self._selected_model(model_dropdown)
        self._translate_thinking = thinking_check.get_active()
        self._regenerate_translation()

    def _regenerate_translation(self):
        self.translated = ""
        self._clear_content()
        self._show_translate_tab()
        self._resize_to_content()
        self._start_translation(self._api_model(self._translate_model), self._translate_thinking, False)

    def _on_explain_regenerate(self, btn, model_dropdown, thinking_check):
        self._explain_model = self._selected_model(model_dropdown)
        self._explain_thinking = thinking_check.get_active()
        self._regenerate_explanation()

    def _regenerate_explanation(self):
        self.explanation = ""
        self._explain_detailed = False
        self._clear_content()
        self._show_explain_tab()
        self._resize_to_content()
        self._start_explanation(self._api_model(self._explain_model), self._explain_thinking)

    def _on_detailed_explain(self, btn):
        self.explanation = ""
        self._clear_content()
        self._show_explain_tab()
        self._resize_to_content()
        self._start_explanation(self._api_model(self._explain_model), self._explain_thinking, detailed=True)

    def _on_retranslate(self, btn):
        buf = self._edit_view.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        new_text = buf.get_text(start, end, False).strip()
        if not new_text:
            return

        self._cancel_active_requests()
        self.text = new_text
        self._editing = False
        self.translated = ""
        self.explanation = ""
        self.chat_messages = []
        self._chat_stream_text = ""
        self._clear_content()
        self._show_translate_tab()
        self._resize_to_content()
        self._ensure_translation()

    def _on_reexplain(self, btn):
        buf = self._edit_view.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        new_text = buf.get_text(start, end, False).strip()
        if not new_text:
            return

        self._cancel_active_requests()
        self.text = new_text
        self._editing = False
        self.translated = ""
        self.explanation = ""
        self.chat_messages = []
        self._chat_stream_text = ""
        self._explain_detailed = False
        self._clear_content()
        self._show_explain_tab()
        self._resize_to_content()
        self._ensure_explanation()

    def _on_copy(self, btn):
        self._copy_translation()
        btn.set_label(BTN_COPIED)
        btn.set_sensitive(False)
        btn.add_css_class("copied")
        GLib.timeout_add_seconds(1, lambda: (btn.remove_css_class("copied"), btn.set_sensitive(True), btn.set_label(BTN_COPY), False)[-1])

    def _copy_translation(self):
        if not self.translated:
            return
        text = self.translated

        def worker():
            copy_text(text)

        threading.Thread(target=worker, daemon=True).start()

    def _on_search(self, btn):
        url = self._search_or_link_url(self.text)
        self._open_url(url)

    def _open_url(self, url):
        def worker():
            try:
                subprocess.run(["xdg-open", url], capture_output=True, timeout=2)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _search_or_link_url(self, text):
        candidate = text.strip()
        parsed = urlparse(candidate)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return candidate
        if " " not in candidate and BARE_DOMAIN_RE.match(candidate):
            return f"https://{candidate}"
        return f"https://www.bing.com/search?q={quote_plus(candidate)}"

    def _on_chat_input_key(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK):
                return False
            self._on_chat_send(self._chat_input)
            return True
        return False

    def _on_chat_send(self, widget):
        if self._chat_loading:
            return

        buf = self._chat_input.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, False).strip()

        if not text:
            return

        buf.set_text("")
        self.chat_messages.append({"role": "user", "content": text})
        self._append_chat_bubble("user", text)


        self._chat_send_btn.set_sensitive(False)
        self._cancel_chat_request()
        cancel_event = threading.Event()
        self._chat_loading = True
        request_text = self.text
        request_model = self._api_model(self._chat_model)
        request_thinking = self._chat_thinking
        request_include_context = self._chat_include_context
        self._chat_request_text = request_text
        self._chat_request_model = request_model
        self._chat_request_thinking = request_thinking
        self._chat_request_include_context = request_include_context
        self._chat_cancel_event = cancel_event
        self._chat_stream_text = ""
        self._chat_stream_view, thinking_align = self._append_chat_bubble("assistant", CHAT_THINKING)

        def worker():
            chunks = []
            for chunk in chat_stream(
                request_text, self.translated, self.explanation,
                self.chat_messages[:-1], text, self.config,
                model=request_model,
                thinking_enabled=request_thinking,
                include_context=request_include_context,
                cancel_event=cancel_event,
            ):
                if cancel_event.is_set():
                    return
                chunks.append(chunk)
                GLib.idle_add(
                    self._on_chat_chunk,
                    request_text,
                    request_model,
                    request_thinking,
                    request_include_context,
                    cancel_event,
                    chunk,
                )
            result = "".join(chunks).strip()
            GLib.idle_add(
                self._on_chat_done,
                request_text,
                request_model,
                request_thinking,
                request_include_context,
                cancel_event,
                result,
                thinking_align,
            )

        threading.Thread(target=worker, daemon=True).start()

    def _is_chat_request_current(self, text, model, thinking_enabled, include_context, cancel_event):
        return (
            cancel_event is not None
            and not cancel_event.is_set()
            and self._chat_cancel_event is cancel_event
            and text == self.text
            and self._chat_model == self._display_model(model)
            and self._chat_thinking == thinking_enabled
            and self._chat_include_context == include_context
            and self._chat_request_text == text
            and self._chat_request_model == model
            and self._chat_request_thinking == thinking_enabled
            and self._chat_request_include_context == include_context
        )

    def _on_chat_chunk(self, text, model, thinking_enabled, include_context, cancel_event, chunk):
        if not self._is_chat_request_current(text, model, thinking_enabled, include_context, cancel_event):
            return False
        if not chunk:
            return False
        if not self._chat_stream_text:
            self._set_text_view_text(self._chat_stream_view, "")
        self._chat_stream_text += chunk
        if self._current_tab == "chat":
            self._append_text_view_text(self._chat_stream_view, chunk)
            self._scroll_chat_to_bottom()
            self._resize_to_content()
        return False

    def _on_chat_done(self, text, model, thinking_enabled, include_context, cancel_event, result, thinking_widget):
        if (
            self._chat_cancel_event is cancel_event
            and self._chat_request_text == text
            and self._chat_request_model == model
            and self._chat_request_thinking == thinking_enabled
            and self._chat_request_include_context == include_context
        ):
            self._chat_loading = False
            self._chat_request_text = None
            self._chat_request_model = None
            self._chat_request_thinking = False
            self._chat_request_include_context = True
            self._chat_cancel_event = None
        if (
            cancel_event.is_set()
            or text != self.text
            or self._chat_model != self._display_model(model)
            or self._chat_thinking != thinking_enabled
            or self._chat_include_context != include_context
        ):
            if self._current_tab == "chat" and self._chat_send_btn is not None:
                self._chat_send_btn.set_sensitive(True)
            return False
        if not result:
            result = self._chat_stream_text.strip()
        self.chat_messages.append({"role": "assistant", "content": result})
        self._chat_stream_text = ""
        self._set_text_view_markdown(self._chat_stream_view, result)
        if self._current_tab == "chat":
            self._chat_send_btn.set_sensitive(True)
            self._scroll_chat_to_bottom()
            self._resize_to_content()
        return False

    def _on_chat_input_changed(self, buf):
        self._resize_to_content()

    def _content_height_limit(self):
        display = Gdk.Display.get_default()
        if display is None:
            return 420
        monitors = display.get_monitors()
        max_h = 900
        if monitors.get_n_items() > 0:
            m = monitors.get_item(0)
            geo = m.get_geometry()
            max_h = int(geo.height * 0.5)
        return max(120, max_h - 110)

    def _resize_to_content(self):
        if self._resize_timeout_id:
            return
        self._resize_timeout_id = GLib.timeout_add(40, self._apply_resize_to_content)

    def _apply_resize_to_content(self):
        self._resize_timeout_id = None
        self._max_content_height = self._content_height_limit()
        if self._content_scroll is not None:
            self._content_scroll.set_max_content_height(self._max_content_height)
        self._refresh_visible_text_heights()

        display = Gdk.Display.get_default()
        max_h = 900
        if display is not None:
            monitors = display.get_monitors()
            if monitors.get_n_items() > 0:
                geo = monitors.get_item(0).get_geometry()
                max_h = int(geo.height * 0.5)

        _min_h, natural_h, _min_baseline, _natural_baseline = self.outer.measure(
            Gtk.Orientation.VERTICAL,
            WINDOW_WIDTH,
        )
        target_h = min(max(180, natural_h), max_h)
        self.set_default_size(WINDOW_WIDTH, target_h)
        self.queue_resize()
        return False

    def _truncate(self, text):
        max_chars = 300
        return text if len(text) <= max_chars else text[:max_chars] + "..."

    def _regenerate_current_tab(self):
        if self._current_tab == "translate" and not self._editing:
            self._regenerate_translation()
            return True
        if self._current_tab == "explain":
            self._regenerate_explanation()
            return True
        return False

    def _toggle_current_thinking(self):
        if self._current_tab == "translate" and not self._editing:
            self._cancel_translation_request()
            self._translate_thinking = not self._translate_thinking
            self._clear_content()
            self._show_translate_tab()
            self._resize_to_content()
            return True
        if self._current_tab == "explain":
            self._cancel_explain_request()
            self._explain_thinking = not self._explain_thinking
            self._clear_content()
            self._show_explain_tab()
            self._resize_to_content()
            return True
        if self._current_tab == "chat":
            self._cancel_chat_request()
            self._chat_thinking = not self._chat_thinking
            self._clear_content()
            self._show_chat_tab()
            self._resize_to_content()
            return True
        return False

    def _on_key(self, controller, keyval, keycode, state):
        self._reset_autoclose_timer()
        if keyval == Gdk.KEY_Escape:
            if self._editing:
                self._on_edit_cancel(self.edit_btn)
                return True
            focused = self.get_focus()
            if isinstance(focused, Gtk.Entry) or (isinstance(focused, Gtk.TextView) and focused.get_editable()):
                self.outer.grab_focus()
                return True
            self.close()
            return True

        focused = self.get_focus()
        if isinstance(focused, Gtk.Entry) or (isinstance(focused, Gtk.TextView) and focused.get_editable()):
            return False

        key = Gdk.keyval_name(keyval)
        if key:
            key = key.lower()

        if key == "s":
            self._switch_tab("translate")
            return True
        elif key == "w":
            self._switch_tab("explain")
            return True
        elif key == "c":
            self._switch_tab("chat")
            return True
        elif key == "e":
            self._on_edit(self.edit_btn)
            return True
        elif key == "r":
            return self._regenerate_current_tab()
        elif key == "y":
            if self._current_tab == "translate" and self.translated:
                self._copy_translation()
                return True
        elif key == "f":
            self._open_url(self._search_or_link_url(self.text))
            return True
        elif key == "t":
            return self._toggle_current_thinking()
        elif key == "x":
            if self._current_tab == "chat":
                self._toggle_chat_context()
                return True

        return False
