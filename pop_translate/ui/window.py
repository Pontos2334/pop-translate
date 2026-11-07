import subprocess
import os
import re
import tempfile
import threading
import time
from urllib.parse import quote_plus, urlparse

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

from ..i18n import (
    APP_TITLE, TRANSLATING, EXPLAINING,
    BTN_COPY_SHORT, BTN_COPIED, BTN_COPIED_ORIG,
    BTN_RETRANSLATE, BTN_REEXPLAIN, BTN_SHORT, BTN_DETAILED,
    BTN_SHORT_EXPLAIN, BTN_DETAILED_EXPLAIN,
    BTN_CANCEL, BTN_THINKING, BTN_RETRY,
    BTN_VISION_CAPTURE, BTN_VISION_SHORT, BTN_VISION_DETAILED,
    VISION_EMPTY_HINT, VISION_EMPTY_TITLE, NO_CONTENT_HINT, NO_CONTENT_TITLE,
    BTN_INPUT_TEXT, SOURCE_LABEL, TRANSLATION_LABEL, EXPLANATION_LABEL,
    VISION_ATTACHMENT_TITLE, VISION_ATTACHMENT_HINT,
    VISION_FIRST_MESSAGE, VISION_FIRST_MESSAGE_DETAILED,
    ERROR_REQUEST_FAILED, ERROR_UNKNOWN,
    TAB_TRANSLATE, TAB_EXPLAIN, TAB_CHAT, TAB_VISION,
    CHAT_THINKING,
    TOOLTIP_EDIT, TOOLTIP_COPY_ORIGINAL, TOOLTIP_SEARCH,
    TOOLTIP_PIN, TOOLTIP_UNPIN, TOOLTIP_HELP, TOOLTIP_CLOSE,
    TOOLTIP_REGEN_TRANSLATE, TOOLTIP_REGEN_EXPLAIN,
    TOOLTIP_VISION_RECAPTURE, TOOLTIP_VIEW_CAPTURE, TOOLTIP_MODEL, TOOLTIP_THINKING,
    TOOLTIP_COPY, TOOLTIP_COPY_EXPLAIN,
    TOOLTIP_EXPAND, TOOLTIP_COLLAPSE,
    BTN_EXPAND, BTN_COLLAPSE,
    EDIT_KEY_HINT, SHORTCUT_HELP_TITLE, SHORTCUT_HELP_NOTE, SHORTCUTS,
)
from ..api import StreamEvent
from ..config import DEFAULTS
from ..translate import translate_stream, explain_stream, chat_stream
from ..vision import vision_stream, vision_chat_stream
from ..clipboard import copy_text
from ..log import get_logger
from .chat_panel import ChatPanel
from .widgets import (
    AutoHeightTextView,
    SpeedStats,
    render_preserving_scroll,
    restore_after_relayout,
    empty_state,
    icon_button,
    icon_image,
    load_styles,
    model_dropdown,
    text_button,
)

logger = get_logger(__name__)

BUILTIN_MODELS = (DEFAULTS["model"], "deepseek-v4-pro")
BUILTIN_VISION_MODELS = (DEFAULTS["vision_model"],)
WINDOW_WIDTH = 680
BARE_DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}([/?#].*)?$")
KWIN_DBUS_DEST = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_IFACE = "org.kde.kwin.Scripting"


class TranslateWindow(Gtk.ApplicationWindow):
    def __init__(self, app, text, config, history_db, default_tab="translate", vision_image_path=None):
        super().__init__(application=app)
        self.set_title(APP_TITLE)
        self.original_text = text
        self.text = text
        self.translated = ""
        self.explanation = ""
        self.vision_result = ""
        self.config = config
        self.history_db = history_db
        self._translate_status_box = None
        self._translate_status_label = None
        self._translate_spinner = None
        self._explain_status_box = None
        self._explain_status_label = None
        self._explain_spinner = None
        self._vision_image_path = (
            vision_image_path if vision_image_path and os.path.exists(vision_image_path) else None
        )
        self._vision_loading = False
        self._vision_cancel_event = None
        self._vision_detailed = False
        self._vision_chat_panel = None
        self._translate_result_view = None
        self._translate_copy_btn = None
        self._explain_result_view = None
        self._explain_copy_btn = None
        self._translate_speed = SpeedStats()
        self._explain_speed = SpeedStats()
        self._translate_error = None
        self._explain_error = None
        self._tab_scroll_positions = {}
        self._edit_view = None
        self._edit_primary_action = None
        self._content_scroll = None
        self._page_toolbar = None
        self._status_kind = None
        self._status_model_dropdown = None
        self._status_thinking_check = None
        self._status_speed_label = None
        self._explain_mode_buttons = None
        self._syncing_status_controls = False
        self._source_label = None
        self._source_toggle_btn = None
        self._source_expanded = False
        self._last_auto_size = None
        self._resize_timeout_id = None
        self._explain_markdown_refresh_id = None
        self._default_tab = default_tab
        self._editing = False
        self._translate_loading = False
        self._explain_loading = False
        self._translate_request_text = None
        self._explain_request_text = None
        self._translate_request_model = None
        self._explain_request_model = None
        self._translate_request_thinking = False
        self._explain_request_thinking = False
        self._translate_cancel_event = None
        self._explain_cancel_event = None
        self._max_content_height = 420
        self._translate_model = self._initial_model()
        self._explain_model = self._initial_model()
        self._translate_thinking = False
        self._explain_thinking = False
        self._explain_detailed = False
        self._vision_context_suppressed = False
        self._chat_panel = None
        self._autoclose_timeout_id = None
        self._pinned = False
        self._closing = False
        self.pin_btn = None
        self._model_choices = self._build_model_choices()
        self._vision_model_choices = self._build_vision_model_choices()
        self.set_decorated(False)
        self.set_resizable(True)
        self.set_size_request(400, -1)
        self.set_default_size(WINDOW_WIDTH, 280)

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
        self._closing = True
        self._cancel_active_requests()
        self._stop_autoclose_timer()
        if self._resize_timeout_id:
            GLib.source_remove(self._resize_timeout_id)
            self._resize_timeout_id = None
        self._cancel_pending_markdown_refreshes()
        if self._chat_panel is not None:
            self._chat_panel.cancel()
        if self._vision_chat_panel is not None:
            self._vision_chat_panel.cancel_pending_refreshes()
            self._vision_chat_panel.cancel()
        self._remove_vision_image()
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
        self._translate_speed.reset()

    def _cancel_explain_request(self):
        if self._explain_cancel_event is not None:
            self._explain_cancel_event.set()
        self._cancel_scheduled_markdown_refresh("_explain_markdown_refresh_id")
        self._explain_cancel_event = None
        self._explain_loading = False
        self._explain_request_text = None
        self._explain_request_model = None
        self._explain_request_thinking = False
        self._explain_speed.reset()

    def _cancel_vision_request(self):
        if self._vision_cancel_event is not None:
            self._vision_cancel_event.set()
        self._vision_cancel_event = None
        self._vision_loading = False
        if self._vision_chat_panel is not None:
            self._vision_chat_panel.cancel()

    def _cancel_active_requests(self):
        self._cancel_translation_request()
        self._cancel_explain_request()
        self._cancel_vision_request()
        if self._chat_panel is not None:
            self._chat_panel.cancel()

    def _start_autoclose_timer(self):
        if getattr(self, "_pinned", False) or getattr(self, "_closing", False):
            return
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

    def _focus_window(self):
        self.present()
        self._focus_current_tab()
        return False

    def _load_css(self):
        load_styles()

    def _build_ui(self):
        self.outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.outer.set_css_classes(["translate-window"])
        self.outer.set_focusable(True)
        self.set_child(self.outer)

        self._build_header()

        self.content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.content_area.set_hexpand(True)
        self.content_area.set_vexpand(True)
        self.outer.append(self.content_area)

        self._build_status_bar()
        self._resize_to_content()

    def _build_header(self):
        """One compact row: brand mark, page tabs, then window actions.

        Window-wide actions only live here; text actions (edit/copy/search)
        live in the source block where they apply, so the header never turns
        into a wall of equally-weighted icons.
        """
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        header.set_css_classes(["app-header"])
        drag_gesture = Gtk.GestureClick.new()
        drag_gesture.set_button(1)
        drag_gesture.connect("pressed", self._on_title_bar_pressed)
        header.add_controller(drag_gesture)

        mark = icon_image("translate-symbolic", 16)
        mark.set_css_classes(["app-mark"])
        mark.set_tooltip_text(APP_TITLE)
        header.append(mark)

        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        tabs.set_margin_start(3)
        header.append(tabs)

        self.tab_btns = {}
        for tab_id, label, icon in [
            ("translate", TAB_TRANSLATE, "translate-symbolic"),
            ("explain", TAB_EXPLAIN, "explain-symbolic"),
            ("chat", TAB_CHAT, "chat-symbolic"),
            ("vision", TAB_VISION, "vision-symbolic"),
        ]:
            btn = icon_button(
                icon, label, label=label, css_classes=("tab-btn",), icon_size=14
            )
            btn.connect("clicked", lambda b, t=tab_id: self._switch_tab(t))
            tabs.append(btn)
            self.tab_btns[tab_id] = btn

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        self.pin_btn = icon_button("pin-symbolic", TOOLTIP_PIN)
        self.pin_btn.connect("clicked", self._on_pin_clicked)
        header.append(self.pin_btn)
        header.append(self._build_help_button())

        close_btn = icon_button("close-symbolic", TOOLTIP_CLOSE, css_classes=("close-btn",))
        close_btn.connect("clicked", lambda b: self.close())
        header.append(close_btn)

        self.header = header
        self.outer.append(header)

    def _build_help_button(self):
        button = icon_button("keyboard-symbolic", TOOLTIP_HELP)
        popover = Gtk.Popover()
        popover.set_has_arrow(False)
        popover.set_position(Gtk.PositionType.BOTTOM)
        popover.set_parent(button)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_size_request(264, -1)
        title = Gtk.Label(label=SHORTCUT_HELP_TITLE, xalign=0)
        title.set_css_classes(["help-title"])
        content.append(title)

        grid = Gtk.Grid(row_spacing=5, column_spacing=14)
        for row, (keys, description) in enumerate(SHORTCUTS):
            key_label = Gtk.Label(label=keys)
            key_label.set_css_classes(["kbd"])
            key_label.set_halign(Gtk.Align.END)
            key_label.set_valign(Gtk.Align.CENTER)
            grid.attach(key_label, 0, row, 1, 1)
            desc_label = Gtk.Label(label=description, xalign=0)
            desc_label.set_css_classes(["help-desc"])
            desc_label.set_wrap(True)
            desc_label.set_max_width_chars(32)
            grid.attach(desc_label, 1, row, 1, 1)
        content.append(grid)

        note = Gtk.Label(label=SHORTCUT_HELP_NOTE, xalign=0)
        note.set_css_classes(["help-desc"])
        note.set_wrap(True)
        note.set_max_width_chars(38)
        note.set_margin_top(2)
        content.append(note)

        popover.set_child(content)
        self._track_popover(popover)
        self.help_popover = popover
        button.connect("clicked", lambda b: popover.popup())
        return button

    def _track_popover(self, popover):
        """A popover should not let the inactivity timer close the window
        while the user is reading shortcuts or inspecting a screenshot."""
        def on_visible(widget, _param):
            if widget.get_visible():
                self._stop_autoclose_timer()
            elif not self._closing:
                self._start_autoclose_timer()

        popover.connect("notify::visible", on_visible)

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

    def _on_pin_clicked(self, _button):
        self._toggle_pin()

    def _toggle_pin(self):
        self._set_pinned(not self._pinned)
        return True

    def _set_pinned(self, pinned):
        if pinned == self._pinned:
            self._refresh_pin_button()
            return True

        self._pinned = pinned
        self._refresh_pin_button()
        if pinned:
            self._stop_autoclose_timer()
        else:
            self._start_autoclose_timer()

        # KWin D-Bus 子进程调用最坏可耗时数秒，放后台线程避免冻结 UI
        def worker():
            ok = self._apply_kwin_keep_above(pinned)
            GLib.idle_add(self._on_pin_applied, pinned, ok)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _on_pin_applied(self, pinned, ok):
        if not ok and self._pinned == pinned:
            self._pinned = not pinned
            self._refresh_pin_button()
            if self._pinned:
                self._stop_autoclose_timer()
            else:
                self._start_autoclose_timer()
            logger.warning("Pop Translate: KDE Wayland 置顶设置失败")
        return False

    def _refresh_pin_button(self):
        if self.pin_btn is None:
            return
        if self._pinned:
            self.pin_btn.set_tooltip_text(TOOLTIP_UNPIN)
            self.pin_btn.add_css_class("pin-active")
        else:
            self.pin_btn.set_tooltip_text(TOOLTIP_PIN)
            self.pin_btn.remove_css_class("pin-active")

    def _apply_kwin_keep_above(self, pinned):
        """同步执行 KWin D-Bus 置顶；仅应在后台线程调用。"""
        script = self._kwin_keep_above_script(pinned)
        plugin_name = f"pop_translate_pin_{os.getpid()}_{id(self)}"
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", prefix="pop_translate_pin_", suffix=".js", delete=False
            ) as f:
                script_path = f.name
                f.write(script)

            self._call_kwin_script_method("unloadScript", plugin_name, check=False)
            self._call_kwin_script_method("loadScript", script_path, plugin_name)
            self._call_kwin_script_method("start")
            # start 后立刻 unload 可能在脚本运行前生效，稍等再清理注册
            time.sleep(0.3)
            self._call_kwin_script_method("unloadScript", plugin_name, check=False)
            return True
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("Pop Translate: KWin D-Bus 调用失败: %s", e)
            return False
        finally:
            if script_path is not None:
                try:
                    os.remove(script_path)
                except OSError:
                    pass

    def _call_kwin_script_method(self, method, *args, check=True):
        cmd = [
            "gdbus",
            "call",
            "--session",
            "--dest",
            KWIN_DBUS_DEST,
            "--object-path",
            KWIN_SCRIPTING_PATH,
            "--method",
            f"{KWIN_SCRIPTING_IFACE}.{method}",
            *args,
        ]
        return subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True,
            timeout=2,
        )

    def _kwin_keep_above_script(self, pinned):
        # 按 pid 匹配本进程窗口，窗口标题可以保持为应用名
        pid = os.getpid()
        keep_above = "true" if pinned else "false"
        return f"""
(function() {{
    const pid = {pid};
    const keepAbove = {keep_above};

    function pidOf(window) {{
        try {{
            return window.pid;
        }} catch (e) {{
            return undefined;
        }}
    }}

    function setKeepAbove(window) {{
        try {{
            if (window.keepAbove !== keepAbove) {{
                window.keepAbove = keepAbove;
            }}
        }} catch (e) {{
            try {{
                workspace.activeWindow = window;
                if (window.keepAbove !== keepAbove && typeof workspace.slotWindowAbove === "function") {{
                    workspace.slotWindowAbove();
                }}
            }} catch (ignored) {{}}
        }}

        try {{
            if (keepAbove) {{
                workspace.activeWindow = window;
            }}
        }} catch (ignored) {{}}
    }}

    const windows = workspace.windowList();
    for (let i = 0; i < windows.length; i++) {{
        const window = windows[i];
        if (pidOf(window) === pid) {{
            setKeepAbove(window);
            break;
        }}
    }}
}})();
    """

    def _on_vision_capture(self, button):
        self.hide()
        # Defer screen capture slightly to ensure window has vanished from screen
        GLib.timeout_add(250, self._start_vision_capture_worker)

    def _start_vision_capture_worker(self):
        def worker():
            from ..__main__ import capture_screenshot, last_captured_image
            success = capture_screenshot()
            if success:
                GLib.idle_add(self._on_vision_captured, last_captured_image())
            else:
                GLib.idle_add(self.show)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _on_vision_captured(self, image_path):
        self._reset_autoclose_timer()
        if image_path and image_path != self._vision_image_path and os.path.exists(image_path):
            self._remove_vision_image()
            self._vision_image_path = image_path
        self._cancel_vision_request()
        if self._vision_chat_panel is not None:
            self._vision_chat_panel.reset()
        self.vision_result = ""
        self._vision_detailed = False
        self._vision_context_suppressed = False
        self._editing = False
        self._edit_view = None
        self.show()
        self._switch_tab("vision")

    def _remove_vision_image(self):
        if self._vision_image_path:
            try:
                os.remove(self._vision_image_path)
            except OSError:
                pass
        self._vision_image_path = None

    def _regenerate_vision(self, detailed=None):
        if not self._vision_image_path:
            return
        if detailed is not None:
            self._vision_detailed = detailed
        self._clear_content()
        self._start_vision_request()
        self._show_vision_tab()
        self._resize_to_content()

    def _ensure_vision_chat_panel(self):
        if self._vision_chat_panel is None:
            self._vision_chat_panel = ChatPanel(
                model_choices=self._vision_model_choices,
                initial_model=self.config.vision_model,
                initial_thinking=False,
                show_thinking=False,
            )
            self._vision_chat_panel.set_callbacks(
                on_request=self._handle_vision_chat_request,
                on_resize=self._request_chat_resize,
                on_settings_changed=self._handle_vision_chat_settings_changed,
                on_clear_context=self._handle_vision_chat_clear_context,
            )
        return self._vision_chat_panel

    def _start_vision_request(self):
        image_path = self._vision_image_path
        if not image_path or not os.path.exists(image_path):
            return
        panel = self._ensure_vision_chat_panel()
        self._cancel_vision_request()
        panel.reset()
        first_message = (
            VISION_FIRST_MESSAGE_DETAILED if self._vision_detailed else VISION_FIRST_MESSAGE
        )
        panel.append_user_message(first_message)
        cancel_event = threading.Event()
        panel.start_stream(cancel_event)
        self._vision_loading = True
        self._vision_cancel_event = cancel_event
        model = self._api_vision_model(panel.model)

        def worker():
            chunks = []
            try:
                for chunk in vision_stream(
                    image_path,
                    self.config,
                    model=model,
                    detailed=self._vision_detailed,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        return
                    if isinstance(chunk, StreamEvent):
                        GLib.idle_add(panel.handle_event, cancel_event, chunk)
                        continue
                    chunks.append(chunk)
                    GLib.idle_add(panel.append_chunk, cancel_event, chunk)
                result = "".join(chunks).strip()
            except Exception as e:
                logger.warning("Pop Translate: 识图请求失败: %s", e)
                GLib.idle_add(panel.fail_stream, cancel_event, str(e) or ERROR_UNKNOWN)
                return
            GLib.idle_add(panel.finish_stream, cancel_event, result)
            GLib.idle_add(self._on_vision_analysis_done, cancel_event, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_vision_analysis_done(self, cancel_event, result):
        if self._vision_cancel_event is not cancel_event:
            return False
        self._vision_loading = False
        self._vision_cancel_event = None
        if not cancel_event.is_set() and result:
            self.vision_result = result
        return False

    def _handle_vision_chat_request(self, panel, messages_before, user_text, settings):
        image_path = self._vision_image_path
        if not image_path or not os.path.exists(image_path):
            return
        cancel_event = threading.Event()
        panel.start_stream(cancel_event)
        model = self._api_vision_model(settings.model)

        def worker():
            chunks = []
            try:
                for chunk in vision_chat_stream(
                    image_path,
                    messages_before,
                    user_text,
                    self.config,
                    model=model,
                    include_context=settings.include_context,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        return
                    if isinstance(chunk, StreamEvent):
                        GLib.idle_add(panel.handle_event, cancel_event, chunk)
                        continue
                    chunks.append(chunk)
                    GLib.idle_add(panel.append_chunk, cancel_event, chunk)
                result = "".join(chunks).strip()
            except Exception as e:
                logger.warning("Pop Translate: 识图对话请求失败: %s", e)
                GLib.idle_add(panel.fail_stream, cancel_event, str(e) or ERROR_UNKNOWN)
                return
            GLib.idle_add(panel.finish_stream, cancel_event, result)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_vision_chat_settings_changed(self, panel):
        pass

    def _handle_vision_chat_clear_context(self, panel):
        self.vision_result = ""

    def _on_copy_original(self, btn):
        text = self.text
        if not text:
            return

        icon = btn.get_child()
        if isinstance(icon, Gtk.Image):
            icon.set_from_icon_name("check-symbolic")
        btn.set_tooltip_text(BTN_COPIED_ORIG)
        btn.add_css_class("copied")
        btn.set_sensitive(False)

        def worker():
            copy_text(text)

            def reset_btn():
                if btn.get_root() is None:
                    return False
                if isinstance(icon, Gtk.Image):
                    icon.set_from_icon_name("copy-symbolic")
                btn.remove_css_class("copied")
                btn.set_tooltip_text(TOOLTIP_COPY_ORIGINAL)
                btn.set_sensitive(True)
                return False

            # GLib 定时器注册非线程安全，先回主线程再安排
            GLib.idle_add(
                lambda: (GLib.timeout_add_seconds(1, reset_btn), False)[1]
            )

        threading.Thread(target=worker, daemon=True).start()

    # -- footer: model / thinking / regenerate --

    def _build_status_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.set_css_classes(["status-bar"])
        self.outer.append(bar)
        self._status_bar = bar
        self._page_toolbar = bar

    def _clear_status_bar(self):
        if self._status_bar is None:
            return
        child = self._status_bar.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._status_bar.remove(child)
            child = nxt
        self._translate_speed.set_label(None)
        self._explain_speed.set_label(None)
        self._status_kind = None
        self._status_model_dropdown = None
        self._status_thinking_check = None
        self._status_speed_label = None
        self._explain_mode_buttons = None

    def _sync_status_bar(self, force=False):
        kind = getattr(self, "_current_tab", self._default_tab)
        # No text means the page is a single call-to-action; model settings
        # would just add chrome below it.
        visible = kind in ("translate", "explain") and not self._editing and bool(self.text)
        self._status_bar.set_visible(visible)
        if not visible:
            if self._status_kind is not None:
                self._clear_status_bar()
            return
        if not force and self._status_kind == kind and self._status_bar.get_first_child() is not None:
            return
        self._populate_status_bar(kind)

    def _populate_status_bar(self, kind):
        self._clear_status_bar()
        is_translate = kind == "translate"
        model = self._translate_model if is_translate else self._explain_model
        thinking = self._translate_thinking if is_translate else self._explain_thinking

        dropdown = model_dropdown(self._model_choices, model, max_chars=18)
        dropdown.set_tooltip_text(f"{TOOLTIP_MODEL}：{model}")
        dropdown.connect(
            "notify::selected",
            self._on_translate_model_changed if is_translate else self._on_explain_model_changed,
        )
        self._status_bar.append(dropdown)
        self._status_model_dropdown = dropdown

        thinking_check = Gtk.CheckButton(label=BTN_THINKING)
        thinking_check.set_css_classes(["thinking-toggle"])
        thinking_check.set_tooltip_text(TOOLTIP_THINKING)
        thinking_check.set_active(thinking)
        thinking_check.connect(
            "toggled",
            self._on_translate_thinking_changed if is_translate else self._on_explain_thinking_changed,
        )
        self._status_bar.append(thinking_check)
        self._status_thinking_check = thinking_check

        speed_label = Gtk.Label(label="")
        speed_label.set_css_classes(["speed-label"])
        speed_label.set_ellipsize(Pango.EllipsizeMode.END)
        speed_label.set_max_width_chars(16)
        speed_label.set_visible(False)
        self._status_bar.append(speed_label)
        self._status_speed_label = speed_label
        speed = self._translate_speed if is_translate else self._explain_speed
        speed.set_label(speed_label)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self._status_bar.append(spacer)

        if not is_translate:
            modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            modes.set_css_classes(["mode-group"])
            modes.set_valign(Gtk.Align.CENTER)
            short_btn = Gtk.Button(label=BTN_SHORT)
            short_btn.set_tooltip_text(BTN_SHORT_EXPLAIN)
            short_btn.set_css_classes(["mode-btn"])
            if not self._explain_detailed:
                short_btn.add_css_class("active")
            short_btn.connect(
                "clicked", self._on_explain_mode_clicked, False, dropdown, thinking_check
            )
            modes.append(short_btn)

            detail_btn = Gtk.Button(label=BTN_DETAILED)
            detail_btn.set_tooltip_text(BTN_DETAILED_EXPLAIN)
            detail_btn.set_css_classes(["mode-btn"])
            if self._explain_detailed:
                detail_btn.add_css_class("active")
            detail_btn.connect(
                "clicked", self._on_explain_mode_clicked, True, dropdown, thinking_check
            )
            modes.append(detail_btn)
            self._status_bar.append(modes)
            self._explain_mode_buttons = (short_btn, detail_btn)

        regen = icon_button(
            "refresh-symbolic",
            TOOLTIP_REGEN_TRANSLATE if is_translate else TOOLTIP_REGEN_EXPLAIN,
        )
        regen.set_sensitive(bool(self.text))
        if is_translate:
            regen.connect("clicked", self._on_translate_regenerate, dropdown, thinking_check)
        else:
            regen.connect("clicked", self._on_explain_regenerate, dropdown, thinking_check)
        self._status_bar.append(regen)

        self._status_kind = kind

    def _clear_content(self):
        self._cancel_pending_markdown_refreshes()
        if self._chat_panel is not None:
            self._chat_panel.cancel_pending_refreshes()
            if self._chat_panel.get_parent() is not None:
                self.content_area.remove(self._chat_panel)
        if self._vision_chat_panel is not None:
            self._vision_chat_panel.cancel_pending_refreshes()
            if self._vision_chat_panel.get_parent() is not None:
                self._vision_chat_panel.get_parent().remove(self._vision_chat_panel)
        while True:
            child = self.content_area.get_first_child()
            if child is None:
                break
            self.content_area.remove(child)
        self._translate_status_box = None
        self._translate_status_label = None
        self._translate_spinner = None
        self._explain_status_box = None
        self._explain_status_label = None
        self._explain_spinner = None
        # Keep the footer speed labels attached: the footer survives page
        # rebuilds (regenerate/error) and must keep streaming stats live.
        # _clear_status_bar detaches them before destroying the widgets.
        self._translate_result_view = None
        self._translate_copy_btn = None
        self._explain_result_view = None
        self._explain_copy_btn = None
        self._source_label = None
        self._source_toggle_btn = None
        self._source_expanded = False
        self._edit_view = None
        self._edit_primary_action = None
        self._content_scroll = None

    def _switch_tab(self, tab_id):
        previous_tab = getattr(self, "_current_tab", None)
        if previous_tab is not None and previous_tab != tab_id:
            if self._content_scroll is not None:
                self._tab_scroll_positions[previous_tab] = (
                    self._content_scroll.get_vadjustment().get_value()
                )
            if self._editing:
                self._commit_pending_edit()

        self._current_tab = tab_id
        for tid, btn in self.tab_btns.items():
            if tid == tab_id:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

        self._clear_content()

        if tab_id == "translate":
            if not self.translated and not self._editing:
                self._ensure_translation()
            self._show_translate_tab()
        elif tab_id == "explain":
            if not self.explanation and not self._editing:
                self._ensure_explanation()
            self._show_explain_tab()
        elif tab_id == "chat":
            self._show_chat_tab()
        elif tab_id == "vision":
            self._show_vision_tab()
            panel = self._vision_chat_panel
            if (
                self._vision_image_path
                and panel is not None
                and not panel.messages
                and not panel.loading
            ):
                self._start_vision_request()

        self._sync_status_bar()

        if tab_id in ("translate", "explain") and tab_id != previous_tab:
            saved = self._tab_scroll_positions.get(tab_id)
            if saved and self._content_scroll is not None:
                restore_after_relayout(
                    self._content_scroll.get_vadjustment(), saved
                )

        if self.get_realized():
            GLib.idle_add(self._focus_current_tab_once)

        self._resize_to_content()

    def _focus_current_tab_once(self):
        self._focus_current_tab()
        return False

    def _focus_current_tab(self):
        tab = getattr(self, "_current_tab", self._default_tab)
        if self._editing and self._edit_view is not None:
            self._edit_view.grab_focus()
            return
        if tab == "chat" and self._chat_panel is not None:
            self._chat_panel.grab_input_focus()
            return
        if tab == "vision" and self._vision_image_path and self._vision_chat_panel is not None:
            self._vision_chat_panel.grab_input_focus()
            return
        self.outer.grab_focus()

    def _ensure_translation(self):
        if not self.text or self._translate_loading or self.translated:
            return
        self._start_translation(
            self._api_model(self._translate_model), self._translate_thinking,
            not self._translate_thinking,
        )

    def _start_translation(self, model, thinking_enabled, use_cache):
        self._cancel_translation_request()
        text = self.text
        cancel_event = threading.Event()
        self._translate_loading = True
        self._translate_error = None
        self._translate_request_text = text
        self._translate_request_model = model
        self._translate_request_thinking = thinking_enabled
        self._translate_cancel_event = cancel_event
        self._translate_speed.start()

        def worker():
            chunks = []
            try:
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
                    if isinstance(chunk, StreamEvent):
                        GLib.idle_add(self._on_translate_stream_event, text, model, thinking_enabled, cancel_event, chunk)
                        continue
                    chunks.append(chunk)
                    GLib.idle_add(self._on_translate_chunk, text, model, thinking_enabled, cancel_event, chunk)
                result = "".join(chunks).strip()
            except Exception as e:
                logger.warning("Pop Translate: 翻译请求失败: %s", e)
                GLib.idle_add(self._on_translate_error, text, model, thinking_enabled, cancel_event, str(e) or ERROR_UNKNOWN)
                return
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

    def _build_vision_model_choices(self):
        choices = []
        for name in (self.config.vision_model, *BUILTIN_VISION_MODELS):
            if name and name not in choices:
                choices.append(name)
        return tuple(choices)

    def _api_model(self, selected_model):
        return None if selected_model == self.config.model else selected_model

    def _api_vision_model(self, selected_model):
        return None if selected_model == self.config.vision_model else selected_model

    def _display_model(self, api_model):
        return api_model or self.config.model

    # -- translate / explain page --

    def _build_source_block(self):
        """Quiet, small context preview. No card/border: the result is the card.

        Long originals clamp to three lines; ``展开`` reveals the rest without
        pushing the translation out of the popup.
        """
        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        block.set_css_classes(["source-block"])

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        head.set_margin_bottom(1)
        label = Gtk.Label(label=SOURCE_LABEL, xalign=0)
        label.set_css_classes(["section-label"])
        label.set_hexpand(True)
        label.set_valign(Gtk.Align.CENTER)
        head.append(label)

        toggle = text_button(
            BTN_COLLAPSE if self._source_expanded else BTN_EXPAND,
            tooltip=TOOLTIP_COLLAPSE if self._source_expanded else TOOLTIP_EXPAND,
        )
        toggle.set_visible(self._source_expanded)
        toggle.connect("clicked", self._on_toggle_source)
        self._source_toggle_btn = toggle
        head.append(toggle)

        copy_btn = icon_button(
            "copy-symbolic", TOOLTIP_COPY_ORIGINAL, css_classes=("mini-btn",), icon_size=14
        )
        copy_btn.connect("clicked", self._on_copy_original)
        head.append(copy_btn)

        search_btn = icon_button(
            "search-symbolic", TOOLTIP_SEARCH, css_classes=("mini-btn",), icon_size=14
        )
        search_btn.connect("clicked", self._on_search)
        head.append(search_btn)

        edit_btn = icon_button(
            "edit-symbolic", TOOLTIP_EDIT, css_classes=("mini-btn",), icon_size=14
        )
        edit_btn.connect("clicked", self._on_edit)
        head.append(edit_btn)
        block.append(head)

        source = Gtk.Label(label=self._source_preview_text())
        source.set_css_classes(["source-text"])
        source.set_wrap(True)
        source.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        source.set_lines(-1 if self._source_expanded else 3)
        source.set_ellipsize(
            Pango.EllipsizeMode.NONE if self._source_expanded else Pango.EllipsizeMode.END
        )
        source.set_selectable(False)
        source.set_xalign(0)
        source.set_hexpand(True)
        source.connect("map", lambda *_: GLib.idle_add(self._sync_source_toggle))
        self._source_label = source
        block.append(source)
        GLib.idle_add(self._sync_source_toggle)

        divider = Gtk.Box()
        divider.set_css_classes(["content-divider"])
        divider.set_valign(Gtk.Align.CENTER)
        block.append(divider)
        return block

    def _source_preview_text(self):
        # 折叠态把换行压成单段：既省高度，也避免 GTK 的 lines 对显式换行
        # 计数不一致；展开态再显示原始排版。
        if self._source_expanded:
            return self.text
        return " ".join(self.text.split())

    def _sync_source_toggle(self):
        """Show 展开 only when the rendered preview is actually truncated.

        Character-count heuristics fail across window widths and CJK/Latin
        mixes; Pango's ellipsized flag reflects the real layout.
        """
        button = self._source_toggle_btn
        label = self._source_label
        if button is None or label is None:
            return False
        if self._source_expanded:
            button.set_visible(True)
        else:
            layout = label.get_layout()
            button.set_visible(bool(layout is not None and layout.is_ellipsized()))
        return False

    def _on_toggle_source(self, _btn):
        self._source_expanded = not self._source_expanded
        if self._source_label is not None:
            self._source_label.set_text(self._source_preview_text())
            self._source_label.set_lines(-1 if self._source_expanded else 3)
            self._source_label.set_ellipsize(
                Pango.EllipsizeMode.NONE if self._source_expanded else Pango.EllipsizeMode.END
            )
        if self._source_toggle_btn is not None:
            self._source_toggle_btn.set_label(
                BTN_COLLAPSE if self._source_expanded else BTN_EXPAND
            )
            self._source_toggle_btn.set_tooltip_text(
                TOOLTIP_COLLAPSE if self._source_expanded else TOOLTIP_EXPAND
            )
        GLib.idle_add(self._sync_source_toggle)
        self._resize_to_content()

    def _build_result_header(self, is_translate, result, loading):
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        head.set_margin_bottom(4)
        title = Gtk.Label(
            label=TRANSLATION_LABEL if is_translate else EXPLANATION_LABEL, xalign=0
        )
        title.set_css_classes(["section-label"])
        title.set_hexpand(True)
        title.set_valign(Gtk.Align.CENTER)
        head.append(title)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        status_box.set_css_classes(["stream-status"])
        status_box.set_valign(Gtk.Align.CENTER)
        status_box.set_visible(False)
        spinner = Gtk.Spinner()
        spinner.set_css_classes(["stream-spinner"])
        spinner.set_size_request(12, 12)
        spinner.set_valign(Gtk.Align.CENTER)
        status_label = Gtk.Label(label="")
        status_label.set_css_classes(["stream-status"])
        status_label.set_ellipsize(Pango.EllipsizeMode.END)
        status_label.set_valign(Gtk.Align.CENTER)
        status_box.append(spinner)
        status_box.append(status_label)
        head.append(status_box)

        copy_btn = text_button(
            BTN_COPY_SHORT,
            tooltip=TOOLTIP_COPY if is_translate else TOOLTIP_COPY_EXPLAIN,
        )
        copy_btn.add_css_class("copy")
        copy_btn.set_visible(bool(result))
        copy_btn.set_sensitive(bool(result) and not loading)
        copy_btn.connect(
            "clicked", self._on_copy if is_translate else self._on_copy_explanation
        )
        head.append(copy_btn)
        return head, status_box, status_label, spinner, copy_btn

    def _build_error_banner(self, error, is_translate):
        banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        banner.set_css_classes(["error-banner"])
        banner.set_margin_bottom(8)
        icon = Gtk.Label(label="⚠")
        icon.set_css_classes(["error-hint"])
        icon.set_valign(Gtk.Align.START)
        banner.append(icon)

        message = Gtk.Label(label=f"{ERROR_REQUEST_FAILED}：{error}")
        message.set_css_classes(["error-hint"])
        message.set_wrap(True)
        message.set_xalign(0)
        message.set_hexpand(True)
        banner.append(message)

        retry = text_button(BTN_RETRY)
        retry.set_valign(Gtk.Align.CENTER)
        retry.connect(
            "clicked",
            self._on_translate_retry if is_translate else self._on_explain_retry,
        )
        banner.append(retry)
        return banner

    def _on_translate_retry(self, _btn):
        self._regenerate_translation()

    def _on_explain_retry(self, _btn):
        self._regenerate_explanation()

    def _show_set_status(self, is_translate, loading, error):
        status_box = self._translate_status_box if is_translate else self._explain_status_box
        status_label = self._translate_status_label if is_translate else self._explain_status_label
        spinner = self._translate_spinner if is_translate else self._explain_spinner
        if status_box is None or status_label is None or spinner is None:
            return
        if loading and not error:
            status_label.set_label(TRANSLATING if is_translate else EXPLAINING)
            status_box.set_visible(True)
            spinner.start()
        else:
            self._hide_status(is_translate)

    def _hide_status(self, is_translate):
        status_box = self._translate_status_box if is_translate else self._explain_status_box
        spinner = self._translate_spinner if is_translate else self._explain_spinner
        if status_box is not None:
            status_box.set_visible(False)
        if spinner is not None:
            spinner.stop()

    def _ensure_explanation(self):
        if not self.text or self._explain_loading or self.explanation:
            return
        self._start_explanation(
            self._api_model(self._explain_model), self._explain_thinking,
            detailed=self._explain_detailed,
        )

    def _start_explanation(self, model, thinking_enabled, detailed=False):
        self._cancel_explain_request()
        text = self.text
        cancel_event = threading.Event()
        self._explain_loading = True
        self._explain_error = None
        self._explain_request_text = text
        self._explain_request_model = model
        self._explain_request_thinking = thinking_enabled
        self._explain_detailed = detailed
        self._explain_cancel_event = cancel_event
        self._explain_speed.start()

        def worker():
            chunks = []
            try:
                for chunk in explain_stream(
                    text,
                    self.config,
                    self.history_db,
                    model=model,
                    thinking_enabled=thinking_enabled,
                    detailed=detailed,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        return
                    if isinstance(chunk, StreamEvent):
                        GLib.idle_add(self._on_explain_stream_event, text, model, thinking_enabled, cancel_event, chunk)
                        continue
                    chunks.append(chunk)
                    GLib.idle_add(self._on_explain_chunk, text, model, thinking_enabled, cancel_event, chunk)
                result = "".join(chunks).strip()
            except Exception as e:
                logger.warning("Pop Translate: 解释请求失败: %s", e)
                GLib.idle_add(self._on_explain_error, text, model, thinking_enabled, cancel_event, str(e) or ERROR_UNKNOWN)
                return
            GLib.idle_add(self._on_explain_done, text, model, thinking_enabled, cancel_event, result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_translate_tab(self):
        self._show_result_page("translate")

    def _show_result_page(self, kind):
        """Translation and explanation share one page layout.

        Order and weight matter: three-line source preview, hairline, then the
        result. All page-level settings move to the footer, out of the way.
        """
        is_translate = kind == "translate"
        if self._editing:
            self._show_edit_mode(
                BTN_RETRANSLATE if is_translate else BTN_REEXPLAIN,
                self._on_retranslate if is_translate else self._on_reexplain,
            )
            return

        self._sync_status_bar()

        if not self.text:
            action = Gtk.Button(label=BTN_INPUT_TEXT)
            action.set_css_classes(["action-btn", "primary"])
            action.connect("clicked", self._on_edit)
            self.content_area.append(empty_state(
                "edit-symbolic", NO_CONTENT_TITLE, NO_CONTENT_HINT, action
            ))
            return

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])
        box.set_valign(Gtk.Align.START)
        box.append(self._build_source_block())

        result = self.translated if is_translate else self.explanation
        loading = self._translate_loading if is_translate else self._explain_loading
        error = self._translate_error if is_translate else self._explain_error

        header, status_box, status_label, spinner, copy_btn = self._build_result_header(
            is_translate, result, loading
        )
        box.append(header)

        if error:
            box.append(self._build_error_banner(error, is_translate))

        view = self._readonly_text_view(
            result,
            ["result"] if is_translate else ["result", "result-explain"],
            min_height=22,
            markdown=not is_translate,
        )
        view.set_visible(bool(result))
        box.append(view)

        if is_translate:
            self._translate_status_box = status_box
            self._translate_status_label = status_label
            self._translate_spinner = spinner
            self._translate_result_view = view
            self._translate_copy_btn = copy_btn
        else:
            self._explain_status_box = status_box
            self._explain_status_label = status_label
            self._explain_spinner = spinner
            self._explain_result_view = view
            self._explain_copy_btn = copy_btn

        self._show_set_status(is_translate, loading, error)
        self.content_area.append(self._wrap_scroll(box))

    def _show_edit_mode(self, primary_label, on_primary):
        self._sync_status_bar()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_css_classes(["content-box"])
        box.set_valign(Gtk.Align.START)

        label = Gtk.Label(label=SOURCE_LABEL, xalign=0)
        label.set_css_classes(["section-label"])
        label.set_margin_bottom(6)
        box.append(label)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_has_frame(False)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(64)
        scrolled.set_max_content_height(180)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_css_classes(["source-edit"])

        self._edit_view = Gtk.TextView()
        self._edit_view.get_buffer().set_text(self.text)
        self._edit_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._edit_view.set_accepts_tab(False)
        edit_key_ctrl = Gtk.EventControllerKey.new()
        edit_key_ctrl.connect("key-pressed", self._on_edit_key)
        self._edit_view.add_controller(edit_key_ctrl)
        scrolled.set_child(self._edit_view)
        box.append(scrolled)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_bar.set_margin_top(10)

        hint = Gtk.Label(label=EDIT_KEY_HINT, xalign=0)
        hint.set_css_classes(["help-desc"])
        hint.set_hexpand(True)
        hint.set_valign(Gtk.Align.CENTER)
        btn_bar.append(hint)

        cancel_btn = Gtk.Button(label=BTN_CANCEL)
        cancel_btn.set_css_classes(["action-btn"])
        cancel_btn.connect("clicked", self._on_edit_cancel)
        btn_bar.append(cancel_btn)

        primary_btn = Gtk.Button(label=primary_label)
        primary_btn.set_css_classes(["action-btn", "primary"])
        primary_btn.connect("clicked", on_primary)
        btn_bar.append(primary_btn)

        box.append(btn_bar)
        self._edit_primary_action = on_primary
        self.content_area.append(self._wrap_scroll(box))
        self._edit_view.grab_focus()

    def _show_explain_tab(self):
        self._show_result_page("explain")

    def _show_chat_tab(self):
        if self._chat_panel is None:
            self._chat_panel = ChatPanel(
                model_choices=self._model_choices,
                initial_model=self._initial_model(),
                initial_thinking=self._translate_thinking,
            )
            self._chat_panel.set_callbacks(
                on_request=self._handle_chat_request,
                on_resize=self._request_chat_resize,
                on_settings_changed=self._handle_chat_settings_changed,
                on_clear_context=self._handle_chat_clear_context,
            )
        self.content_area.append(self._chat_panel)

    def _show_vision_tab(self):
        if not self._vision_image_path:
            capture_btn = icon_button(
                "camera-symbolic", BTN_VISION_CAPTURE, label=BTN_VISION_CAPTURE,
                css_classes=("action-btn", "primary"),
            )
            capture_btn.connect("clicked", self._on_vision_capture)
            self.content_area.append(empty_state(
                "vision-symbolic", VISION_EMPTY_TITLE, VISION_EMPTY_HINT, capture_btn
            ))
            return

        attachment = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        attachment.set_css_classes(["vision-attachment"])

        preview_button = Gtk.MenuButton()
        preview_button.set_css_classes(["vision-thumb"])
        preview_button.set_tooltip_text(TOOLTIP_VIEW_CAPTURE)
        preview_button.set_valign(Gtk.Align.CENTER)
        preview_button.set_child(self._build_vision_preview(self._vision_image_path, 44, 32))
        popover = Gtk.Popover()
        popover.set_child(self._build_vision_preview(self._vision_image_path, 520, 280))
        self._track_popover(popover)
        preview_button.set_popover(popover)
        attachment.append(preview_button)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=VISION_ATTACHMENT_TITLE, xalign=0)
        title.set_css_classes(["attachment-title"])
        info.append(title)
        hint = Gtk.Label(label=VISION_ATTACHMENT_HINT, xalign=0)
        hint.set_ellipsize(Pango.EllipsizeMode.END)
        hint.set_css_classes(["attachment-hint"])
        info.append(hint)
        attachment.append(info)

        modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        modes.set_css_classes(["mode-group"])
        modes.set_valign(Gtk.Align.CENTER)
        short_btn = Gtk.Button(label=BTN_VISION_SHORT)
        short_btn.set_css_classes(["mode-btn"])
        if not self._vision_detailed:
            short_btn.add_css_class("active")
        short_btn.connect("clicked", lambda b: self._regenerate_vision(detailed=False))
        modes.append(short_btn)
        detail_btn = Gtk.Button(label=BTN_VISION_DETAILED)
        detail_btn.set_css_classes(["mode-btn"])
        if self._vision_detailed:
            detail_btn.add_css_class("active")
        detail_btn.connect("clicked", lambda b: self._regenerate_vision(detailed=True))
        modes.append(detail_btn)
        attachment.append(modes)

        recapture = icon_button("camera-symbolic", TOOLTIP_VISION_RECAPTURE)
        recapture.connect("clicked", self._on_vision_capture)
        attachment.append(recapture)

        panel = self._ensure_vision_chat_panel()
        panel.set_attachment(attachment)
        self.content_area.append(panel)

    def _build_vision_preview(self, path, max_w=44, max_h=32):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, max_w, max_h, True
            )
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            preview = Gtk.Picture.new_for_paintable(texture)
            preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        except Exception:
            preview = Gtk.Image.new_from_icon_name("image-missing-symbolic")
        preview.set_css_classes(["vision-image"])
        preview.set_halign(Gtk.Align.START)
        preview.set_valign(Gtk.Align.CENTER)
        return preview

    def _handle_chat_settings_changed(self, panel):
        self._translate_thinking = panel.thinking
        self._explain_thinking = panel.thinking

    def _handle_chat_clear_context(self, panel):
        self.text = ""
        self.translated = ""
        self.explanation = ""
        self._vision_context_suppressed = True
        self._cancel_translation_request()
        self._cancel_explain_request()

    def _handle_chat_request(self, panel, messages_before, user_text, settings):
        cancel_event = threading.Event()
        panel.start_stream(cancel_event)
        request_model = self._api_model(settings.model)
        request_text = self.text
        request_translated = self.translated
        request_explanation = self.explanation
        request_vision = "" if self._vision_context_suppressed else self.vision_result

        def worker():
            chunks = []
            try:
                for chunk in chat_stream(
                    request_text,
                    request_translated,
                    request_explanation,
                    messages_before,
                    user_text,
                    self.config,
                    model=request_model,
                    thinking_enabled=settings.thinking_enabled,
                    include_context=settings.include_context,
                    vision_result=request_vision,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        return
                    if isinstance(chunk, StreamEvent):
                        GLib.idle_add(panel.handle_event, cancel_event, chunk)
                        continue
                    chunks.append(chunk)
                    GLib.idle_add(panel.append_chunk, cancel_event, chunk)
                result = "".join(chunks).strip()
            except Exception as e:
                logger.warning("Pop Translate: 对话请求失败: %s", e)
                GLib.idle_add(panel.fail_stream, cancel_event, str(e) or ERROR_UNKNOWN)
                return
            GLib.idle_add(panel.finish_stream, cancel_event, result)

        threading.Thread(target=worker, daemon=True).start()

    def _request_chat_resize(self, _panel):
        self._resize_to_content()

    def _reset_chat(self):
        if self._chat_panel is not None:
            self._chat_panel.reset()

    def _wrap_scroll(self, child):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_has_frame(False)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_min_content_height(48)
        scrolled.set_vexpand(True)
        self._max_content_height = self._content_height_limit()
        scrolled.set_max_content_height(self._max_content_height)
        scrolled.set_child(child)
        self._content_scroll = scrolled
        return scrolled

    def _readonly_text_view(self, text, css_classes, min_height=24, markdown=False, width=None):
        return AutoHeightTextView(
            text,
            css_classes,
            min_height=min_height,
            markdown=markdown,
            max_width=width,
            on_resize=lambda _v: self._resize_to_content(),
        )

    def _set_text_view_text(self, view, text):
        if view is None:
            return
        view.set_plain_text(text)
        view.set_visible(bool(text))

    def _append_text_view_text(self, view, text):
        if view is None or not text:
            return
        view.set_visible(True)
        buf = view.get_buffer()
        end = buf.get_end_iter()
        buf.insert(end, text)

    def _cancel_scheduled_markdown_refresh(self, attr_name):
        source_id = getattr(self, attr_name, None)
        if source_id:
            GLib.source_remove(source_id)
            setattr(self, attr_name, None)

    def _cancel_pending_markdown_refreshes(self):
        self._cancel_scheduled_markdown_refresh("_explain_markdown_refresh_id")

    def _schedule_explain_markdown_refresh(self):
        if self._explain_markdown_refresh_id or self._current_tab != "explain":
            return
        self._explain_markdown_refresh_id = GLib.timeout_add(
            200,
            self._refresh_explain_markdown,
        )

    def _refresh_explain_markdown(self):
        self._explain_markdown_refresh_id = None
        if self._current_tab == "explain" and self._explain_result_view is not None:
            view = self._explain_result_view
            view.set_visible(bool(self.explanation))
            text = self.explanation
            render_preserving_scroll(
                self._content_scroll, lambda: view.set_markdown_text(text)
            )
        return False

    def set_translation(self, translated):
        self.translated = translated
        if self._current_tab == "translate" and not self._editing:
            self._set_text_view_text(self._translate_result_view, translated)
            self._hide_status(True)
            if self._translate_copy_btn is not None:
                self._translate_copy_btn.set_visible(bool(translated))
                self._translate_copy_btn.set_sensitive(bool(translated))
            self._resize_to_content()

    def set_explanation(self, explanation):
        self.explanation = explanation
        self._cancel_scheduled_markdown_refresh("_explain_markdown_refresh_id")
        if self._current_tab == "explain" and self._explain_result_view is not None:
            view = self._explain_result_view
            view.set_visible(bool(explanation))
            if self._explain_copy_btn is not None:
                self._explain_copy_btn.set_visible(bool(explanation))
                self._explain_copy_btn.set_sensitive(bool(explanation))
            render_preserving_scroll(
                self._content_scroll, lambda: view.set_markdown_text(explanation)
            )

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

    def _on_translate_stream_event(self, text, model, thinking_enabled, cancel_event, event):
        if not self._is_translate_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if event.kind == "cached":
            self._translate_speed.mark_cached()
        elif event.kind == "usage":
            self._translate_speed.record_usage(event.data)
        return False

    def _on_explain_stream_event(self, text, model, thinking_enabled, cancel_event, event):
        if not self._is_explain_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if event.kind == "cached":
            self._explain_speed.mark_cached()
        elif event.kind == "usage":
            self._explain_speed.record_usage(event.data)
        elif event.kind == "reasoning":
            self._on_explain_reasoning(text, model, thinking_enabled, cancel_event)
        return False

    def _on_translate_chunk(self, text, model, thinking_enabled, cancel_event, chunk):
        if not self._is_translate_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if not chunk:
            return False
        self._translate_speed.record_chunk(chunk)
        self._translate_error = None
        self.translated += chunk
        if self._current_tab == "translate" and not self._editing:
            self._hide_status(True)
            self._append_text_view_text(self._translate_result_view, chunk)
            if self._translate_copy_btn is not None:
                self._translate_copy_btn.set_visible(True)
                self._translate_copy_btn.set_sensitive(True)
            self._resize_to_content()
        return False

    def _on_explain_chunk(self, text, model, thinking_enabled, cancel_event, chunk):
        if not self._is_explain_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if not chunk:
            return False
        self._explain_speed.record_chunk(chunk)
        self._explain_error = None
        self.explanation += chunk
        if self._current_tab == "explain":
            self._hide_status(False)
            if self._explain_copy_btn is not None:
                self._explain_copy_btn.set_visible(True)
                self._explain_copy_btn.set_sensitive(True)
            self._schedule_explain_markdown_refresh()
        return False

    def _on_explain_reasoning(self, text, model, thinking_enabled, cancel_event):
        if not self._is_explain_request_current(text, model, thinking_enabled, cancel_event):
            return False
        if (
            self._current_tab == "explain"
            and self._explain_status_box is not None
            and self._explain_status_box.get_visible()
            and self._explain_status_label is not None
        ):
            self._explain_status_label.set_label(CHAT_THINKING)
        return False

    def _finish_translate_request_state(self):
        self._translate_loading = False
        self._translate_request_text = None
        self._translate_request_model = None
        self._translate_request_thinking = False
        self._translate_cancel_event = None

    def _finish_explain_request_state(self):
        self._explain_loading = False
        self._explain_request_text = None
        self._explain_request_model = None
        self._explain_request_thinking = False
        self._explain_cancel_event = None

    def _on_translate_done(self, text, model, thinking_enabled, cancel_event, result):
        if (
            self._translate_cancel_event is cancel_event
            and self._translate_request_text == text
            and self._translate_request_model == model
            and self._translate_request_thinking == thinking_enabled
        ):
            self._finish_translate_request_state()
        if (
            cancel_event.is_set()
            or text != self.text
            or self._translate_model != self._display_model(model)
            or self._translate_thinking != thinking_enabled
        ):
            return False
        if self._current_tab == "translate" and not self._editing:
            self._hide_status(True)
        self._translate_speed.finish()
        self.set_translation(result)
        return False

    def _on_explain_done(self, text, model, thinking_enabled, cancel_event, result):
        if (
            self._explain_cancel_event is cancel_event
            and self._explain_request_text == text
            and self._explain_request_model == model
            and self._explain_request_thinking == thinking_enabled
        ):
            self._finish_explain_request_state()
        if (
            cancel_event.is_set()
            or text != self.text
            or self._explain_model != self._display_model(model)
            or self._explain_thinking != thinking_enabled
        ):
            return False
        if self._current_tab == "explain":
            self._hide_status(False)
        self._explain_speed.finish()
        self.set_explanation(result)
        return False

    def _on_translate_error(self, text, model, thinking_enabled, cancel_event, error):
        if not self._is_translate_request_current(text, model, thinking_enabled, cancel_event):
            return False
        self._finish_translate_request_state()
        self._translate_error = error
        self._translate_speed.reset()
        if self._current_tab == "translate" and not self._editing:
            self._clear_content()
            self._show_translate_tab()
            self._resize_to_content()
        return False

    def _on_explain_error(self, text, model, thinking_enabled, cancel_event, error):
        if not self._is_explain_request_current(text, model, thinking_enabled, cancel_event):
            return False
        self._finish_explain_request_state()
        self._explain_error = error
        self._explain_speed.reset()
        if self._current_tab == "explain":
            self._clear_content()
            self._show_explain_tab()
            self._resize_to_content()
        return False

    def _on_edit(self, btn):
        if self._current_tab not in ("translate", "explain"):
            return
        self._editing = True
        self._clear_content()
        self._refresh_current_tab()
        self._resize_to_content()

    def _on_edit_cancel(self, btn):
        self._editing = False
        self._edit_view = None
        self._clear_content()
        self._refresh_current_tab()
        self._resize_to_content()
        self._focus_current_tab()

    def _commit_pending_edit(self):
        """切出编辑态：把编辑中的内容写回原文，回到翻译/解释时自动重译。"""
        view = self._edit_view
        if view is not None:
            buf = view.get_buffer()
            new_text = buf.get_text(
                buf.get_start_iter(), buf.get_end_iter(), False
            ).strip()
            if new_text and new_text != self.text:
                self.text = new_text
                self.translated = ""
                self.explanation = ""
                self._reset_chat()
                self._cancel_translation_request()
                self._cancel_explain_request()
        self._editing = False
        self._edit_view = None

    def _refresh_current_tab(self):
        tab = getattr(self, "_current_tab", self._default_tab)
        if tab == "translate":
            self._show_translate_tab()
        elif tab == "explain":
            self._show_explain_tab()
        elif tab == "chat":
            self._show_chat_tab()
        elif tab == "vision":
            self._show_vision_tab()
        self._sync_status_bar()

    def _on_edit_key(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self._on_edit_cancel(None)
            return True
        if (
            keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
            and state & Gdk.ModifierType.CONTROL_MASK
        ):
            if self._edit_primary_action is not None:
                self._edit_primary_action(None)
            return True
        return False

    def _on_translate_regenerate(self, btn, model_dropdown, thinking_check):
        self._translate_model = self._selected_model(model_dropdown)
        self._translate_thinking = thinking_check.get_active()
        self._explain_thinking = self._translate_thinking
        if self._chat_panel is not None:
            self._chat_panel.set_thinking(self._translate_thinking)
        self._regenerate_translation()

    def _on_explain_regenerate(self, btn, model_dropdown, thinking_check):
        self._explain_model = self._selected_model(model_dropdown)
        self._explain_thinking = thinking_check.get_active()
        self._translate_thinking = self._explain_thinking
        if self._chat_panel is not None:
            self._chat_panel.set_thinking(self._explain_thinking)
        self._regenerate_explanation(detailed=self._explain_detailed)

    def _on_explain_mode_clicked(self, btn, detailed, model_dropdown, thinking_check):
        if detailed == self._explain_detailed:
            return
        self._explain_model = self._selected_model(model_dropdown)
        self._explain_thinking = thinking_check.get_active()
        self._translate_thinking = self._explain_thinking
        if self._chat_panel is not None:
            self._chat_panel.set_thinking(self._explain_thinking)
        self._regenerate_explanation(detailed=detailed)
        self._refresh_explain_mode_buttons()

    def _refresh_explain_mode_buttons(self):
        buttons = getattr(self, "_explain_mode_buttons", None)
        if not buttons:
            return
        short_btn, detail_btn = buttons
        if self._explain_detailed:
            short_btn.remove_css_class("active")
            detail_btn.add_css_class("active")
        else:
            short_btn.add_css_class("active")
            detail_btn.remove_css_class("active")

    def _regenerate_translation(self):
        self.translated = ""
        self._clear_content()
        self._start_translation(self._api_model(self._translate_model), self._translate_thinking, False)
        self._show_translate_tab()
        self._resize_to_content()

    def _on_translate_model_changed(self, dropdown, _param):
        if self._syncing_status_controls:
            return
        self._translate_model = self._selected_model(dropdown)
        if self._translate_loading:
            self._regenerate_translation()

    def _on_translate_thinking_changed(self, check):
        if self._syncing_status_controls:
            return
        self._translate_thinking = check.get_active()
        self._explain_thinking = self._translate_thinking
        if self._chat_panel is not None:
            self._chat_panel.set_thinking(self._translate_thinking)
        if self._translate_loading:
            self._regenerate_translation()

    def _on_explain_model_changed(self, dropdown, param):
        if self._syncing_status_controls:
            return
        self._explain_model = self._selected_model(dropdown)
        self._restart_explain_if_loading()

    def _on_explain_thinking_changed(self, thinking_check):
        if self._syncing_status_controls:
            return
        self._explain_thinking = thinking_check.get_active()
        self._translate_thinking = self._explain_thinking
        if self._chat_panel is not None:
            self._chat_panel.set_thinking(self._explain_thinking)
        self._restart_explain_if_loading()

    def _restart_explain_if_loading(self):
        """加载中变更模型/思考：取消并立即用新设置重启，而非静默空白。"""
        if not self._explain_loading:
            return False
        self._cancel_explain_request()
        self.explanation = ""
        if self._current_tab == "explain":
            self._ensure_explanation()
            self._clear_content()
            self._show_explain_tab()
            self._resize_to_content()
        return True

    def _regenerate_explanation(self, detailed=None):
        if detailed is None:
            detailed = self._explain_detailed
        self.explanation = ""
        self._explain_detailed = detailed
        self._clear_content()
        self._start_explanation(self._api_model(self._explain_model), self._explain_thinking, detailed=detailed)
        self._show_explain_tab()
        self._resize_to_content()

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
        self._edit_view = None
        self.translated = ""
        self.explanation = ""
        self._reset_chat()
        self._clear_content()
        self._ensure_translation()
        self._show_translate_tab()
        self._resize_to_content()
        self._focus_current_tab()

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
        self._edit_view = None
        self.translated = ""
        self.explanation = ""
        self._explain_detailed = False
        self._reset_chat()
        self._clear_content()
        self._ensure_explanation()
        self._show_explain_tab()
        self._resize_to_content()
        self._focus_current_tab()

    def _on_copy(self, btn):
        self._copy_translation()
        btn.set_label(BTN_COPIED)
        btn.set_sensitive(False)
        btn.add_css_class("copied")

        def reset_btn():
            if btn.get_root() is None:
                return False
            btn.remove_css_class("copied")
            btn.set_sensitive(True)
            btn.set_label(BTN_COPY_SHORT)
            return False

        GLib.timeout_add_seconds(1, reset_btn)

    def _on_copy_explanation(self, btn):
        if not self.explanation:
            return
        text = self.explanation

        def worker():
            copy_text(text)

        threading.Thread(target=worker, daemon=True).start()
        btn.set_label(BTN_COPIED)
        btn.set_sensitive(False)
        btn.add_css_class("copied")

        def reset_btn():
            if btn.get_root() is None:
                return False
            btn.remove_css_class("copied")
            btn.set_sensitive(True)
            btn.set_label(BTN_COPY_SHORT)
            return False

        GLib.timeout_add_seconds(1, reset_btn)

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

    def _current_monitor(self):
        display = Gdk.Display.get_default()
        if display is None:
            return None
        surface = self.get_surface() if self.get_realized() else None
        if surface is not None:
            monitor = display.get_monitor_at_surface(surface)
            if monitor is not None:
                return monitor
        monitors = display.get_monitors()
        if monitors.get_n_items() > 0:
            return monitors.get_item(0)
        return None

    def _window_height_limit(self):
        monitor = self._current_monitor()
        if monitor is None:
            return 720
        return max(240, min(760, int(monitor.get_geometry().height * 0.78)))

    def _content_height_limit(self):
        width = max(480, self.get_width())
        chrome = 0
        child = self.outer.get_first_child()
        while child is not None:
            if child is not self.content_area and child.get_visible():
                chrome += child.measure(Gtk.Orientation.VERTICAL, width)[1]
            child = child.get_next_sibling()
        return max(100, self._window_height_limit() - chrome - 2)

    def _resize_to_content(self):
        if self._resize_timeout_id:
            return
        self._resize_timeout_id = GLib.timeout_add(40, self._apply_resize_to_content)

    def _apply_resize_to_content(self):
        self._resize_timeout_id = None
        self._max_content_height = self._content_height_limit()
        if self._content_scroll is not None:
            self._content_scroll.set_max_content_height(max(80, self._max_content_height))
        for panel in (self._chat_panel, self._vision_chat_panel):
            if panel is not None and panel.get_mapped():
                panel.set_content_height_limit(self._max_content_height)
        if self._source_label is not None:
            GLib.idle_add(self._sync_source_toggle)

        # 用窗口当前实际宽度测量：用户手动缩放后仍按初始宽度计算会得到错误高度
        width = self.get_width()
        if width <= 1:
            width = WINDOW_WIDTH
        _min_h, natural_h, _min_baseline, _natural_baseline = self.outer.measure(
            Gtk.Orientation.VERTICAL,
            width,
        )
        target_h = min(max(180, natural_h), self._window_height_limit())
        target = (width, target_h)
        if target != self._last_auto_size:
            self._last_auto_size = target
            self.set_default_size(*target)
        return False

    def _regenerate_current_tab(self):
        if self._current_tab == "translate" and not self._editing:
            self._regenerate_translation()
            return True
        if self._current_tab == "explain":
            self._regenerate_explanation()
            return True
        if self._current_tab == "vision" and self._vision_image_path:
            self._regenerate_vision()
            return True
        return False

    def _toggle_current_thinking(self):
        if self._current_tab == "translate" and not self._editing:
            self._translate_thinking = not self._translate_thinking
            self._explain_thinking = self._translate_thinking
            if self._chat_panel is not None:
                self._chat_panel.set_thinking(self._translate_thinking)
            # 取消后立即按新模式重译，而不是停留在过期的加载提示
            self._regenerate_translation()
            self._sync_status_bar(force=True)
            return True
        if self._current_tab == "explain":
            self._explain_thinking = not self._explain_thinking
            self._translate_thinking = self._explain_thinking
            if self._chat_panel is not None:
                self._chat_panel.set_thinking(self._explain_thinking)
            self._regenerate_explanation()
            self._sync_status_bar(force=True)
            return True
        if self._current_tab == "chat":
            if self._chat_panel is not None:
                self._chat_panel.toggle_thinking()
            return True
        return False

    def _on_key(self, controller, keyval, keycode, state):
        self._reset_autoclose_timer()
        if keyval == Gdk.KEY_Escape:
            if self._chat_panel is not None and self._chat_panel.loading:
                self._chat_panel.cancel()
                return True
            if (
                self._current_tab == "vision"
                and self._vision_chat_panel is not None
                and self._vision_chat_panel.loading
            ):
                self._cancel_vision_request()
                return True
            if self._editing:
                self._on_edit_cancel(None)
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
        elif key == "v":
            self._switch_tab("vision")
            return True
        elif key == "e":
            self._on_edit(None)
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
        elif key == "p":
            return self._toggle_pin()
        elif key == "t":
            return self._toggle_current_thinking()
        elif key == "x":
            if self._current_tab == "chat":
                if self._chat_panel is not None:
                    self._chat_panel.toggle_context()
                return True
            if (
                self._current_tab == "vision"
                and self._vision_image_path is not None
                and self._vision_chat_panel is not None
            ):
                self._vision_chat_panel.toggle_context()
                return True

        return False
