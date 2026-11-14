import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gdk, Gtk, Pango

from ..clipboard import copy_text
from ..i18n import (
    BTN_CANCEL,
    BTN_CONFIRM_EDIT,
    BTN_EDIT_MSG,
    BTN_REGENERATE,
    BTN_SEND,
    BTN_THINKING,
    BTN_CONTEXT,
    BTN_WITH_CONTEXT,
    BTN_NO_CONTEXT,
    CHAT_THINKING,
    CHAT_PLACEHOLDER,
    CHAT_REASONING_TITLE,
    ERROR_REQUEST_FAILED,
    BTN_COPY_MSG,
    BTN_COPIED_MSG,
    BTN_STOP,
    CHAT_EMPTY_TITLE,
    CHAT_EMPTY_HINT,
    CHAT_INPUT_HINT,
    TOOLTIP_THINKING,
    TOOLTIP_CLEAR,
)
from .widgets import (
    STREAM_MARKDOWN_REFRESH_DELAY_MS,
    AutoHeightTextView,
    SpeedStats,
    attach_placeholder,
    empty_state,
    icon_button,
    model_dropdown,
    render_preserving_scroll,
    restore_after_relayout,
)

CHAT_BUBBLE_MAX_WIDTH = 520
CHAT_USER_BUBBLE_MAX_WIDTH = 440


class ChatMessage:
    __slots__ = ("role", "content")

    def __init__(self, role, content):
        self.role = role
        self.content = content

    def to_dict(self):
        return {"role": self.role, "content": self.content}


class ChatSettings:
    __slots__ = ("model", "thinking_enabled", "include_context")

    def __init__(self, model, thinking_enabled=False, include_context=True):
        self.model = model
        self.thinking_enabled = thinking_enabled
        self.include_context = include_context


class ChatPanel(Gtk.Box):
    def __init__(
        self,
        model_choices,
        initial_model,
        initial_thinking=False,
        initial_include_context=True,
        show_thinking=True,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._model_choices = tuple(model_choices)
        self._model = initial_model
        self._thinking = initial_thinking
        self._include_context = initial_include_context
        self._show_thinking = show_thinking

        self.messages = []

        self._bubble_data = []
        self._loading = False
        self._cancel_event = None
        self._stream_text = ""
        self._stream_reasoning = ""
        self._stream_view = None

        self._speed = SpeedStats()

        self._markdown_refresh_id = None

        self._on_request_cb = None
        self._on_resize_cb = None
        self._on_settings_changed_cb = None
        self._on_clear_context_cb = None

        self._build_ui()

    # -- public api --

    def set_callbacks(
        self,
        *,
        on_request=None,
        on_resize=None,
        on_settings_changed=None,
        on_clear_context=None,
    ):
        self._on_request_cb = on_request
        self._on_resize_cb = on_resize
        self._on_settings_changed_cb = on_settings_changed
        self._on_clear_context_cb = on_clear_context

    @property
    def loading(self):
        return self._loading

    @property
    def model(self):
        return self._model

    @property
    def thinking(self):
        return self._thinking

    @property
    def include_context(self):
        return self._include_context

    @property
    def stream_text(self):
        return self._stream_text

    def current_settings(self):
        return ChatSettings(self._model, self._thinking, self._include_context)

    def set_model(self, model):
        self._model = model
        if hasattr(self, "_model_dropdown"):
            self._select_model(self._model_dropdown, model)

    def set_thinking(self, enabled):
        self._thinking = enabled
        if hasattr(self, "_thinking_check"):
            self._thinking_check.set_active(enabled)

    def toggle_thinking(self):
        self._thinking = not self._thinking
        if hasattr(self, "_thinking_check"):
            self._thinking_check.set_active(self._thinking)
        self._handle_settings_change()

    def toggle_context(self):
        self._include_context = not self._include_context
        self._update_context_button()
        self._handle_settings_change()

    def append_user_message(self, text):
        """以编程方式追加一条用户消息气泡(不触发请求)。"""
        text = (text or "").strip()
        if not text:
            return
        self.messages.append(ChatMessage("user", text))
        self._append_bubble("user", text)

    def start_stream(self, cancel_event):
        self._cancel_event = cancel_event
        self._loading = True
        self._stream_text = ""
        self._stream_reasoning = ""
        self._update_send_button()
        self._set_bubble_actions_sensitive(False)
        self._stream_view, _ = self._append_bubble("assistant", "")
        self._stream_view.set_plain_text(CHAT_THINKING)
        self._bubble_data[-1]["action_box"].set_visible(False)
        if self._bubble_data:
            last = self._bubble_data[-1]
            last["is_stream"] = True
            if last["thinking_container"] is not None:
                last["thinking_container"].set_expanded(True)
                if self._thinking:
                    last["thinking_container"].set_visible(True)
                    last["thinking_view"].set_plain_text(CHAT_THINKING)
                else:
                    last["thinking_container"].set_visible(False)
        self._speed.start()

    def append_chunk(self, cancel_event, chunk):
        if cancel_event is not self._cancel_event or cancel_event.is_set():
            return
        if not chunk:
            return
        self._speed.record_chunk(chunk)
        if self._bubble_data:
            last = self._bubble_data[-1]
            if last.get("is_stream") and last["thinking_container"] is not None:
                if not self._stream_reasoning:
                    last["thinking_container"].set_visible(False)
        if not self._stream_text:
            self._stream_view.set_plain_text("")
        self._stream_text += chunk
        self._schedule_markdown_refresh()

    def handle_event(self, cancel_event, event):
        if cancel_event is not self._cancel_event or cancel_event.is_set():
            return
        if event.kind == "usage":
            self._speed.record_usage(event.data)
        elif event.kind == "reasoning":
            if not self._thinking:
                return
            if self._bubble_data:
                last = self._bubble_data[-1]
                if last.get("is_stream") and last["thinking_container"] is not None:
                    if not self._stream_reasoning:
                        last["thinking_view"].set_plain_text("")
                    self._stream_reasoning += event.text
                    last["thinking_view"].set_plain_text(self._stream_reasoning)
                    last["thinking_container"].set_visible(True)
                    last["thinking_container"].set_expanded(True)

    def finish_stream(self, cancel_event, result):
        if cancel_event is not self._cancel_event:
            return
        if cancel_event.is_set():
            return
        if not result:
            result = self._stream_text.strip()
        self.messages.append(ChatMessage("assistant", result))
        self._stream_text = ""
        stream_view = self._stream_view
        self._stream_view = None
        self._cancel_markdown_refresh()
        if stream_view is not None:
            render_preserving_scroll(
                self._scroll, lambda: stream_view.set_markdown_text(result)
            )
        self._loading = False
        self._cancel_event = None
        self._update_send_button()
        self._set_bubble_actions_sensitive(True)
        self._speed.finish()
        if self._bubble_data:
            last = self._bubble_data[-1]
            last["is_stream"] = False
            last["action_box"].set_visible(True)
            if last.get("thinking_container") is not None:
                last["thinking_container"].set_expanded(False)

    def fail_stream(self, cancel_event, error):
        """流式请求异常终止：复位状态并把错误作为一条消息展示。"""
        if cancel_event is not self._cancel_event or cancel_event.is_set():
            return
        message = f"⚠ {ERROR_REQUEST_FAILED}：{error}"
        self.messages.append(ChatMessage("assistant", message))
        self._stream_text = ""
        stream_view = self._stream_view
        self._stream_view = None
        self._cancel_markdown_refresh()
        self._loading = False
        self._cancel_event = None
        self._update_send_button()
        self._set_bubble_actions_sensitive(True)
        self._speed.reset()
        if self._bubble_data and self._bubble_data[-1].get("is_stream"):
            last = self._bubble_data[-1]
            last["is_stream"] = False
            last["action_box"].set_visible(True)
            if last["thinking_container"] is not None:
                last["thinking_container"].set_visible(False)
            if stream_view is not None:
                render_preserving_scroll(
                    self._scroll, lambda: stream_view.set_markdown_text(message)
                )

    def cancel(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_markdown_refresh()
        self._remove_stream_bubble()
        self._loading = False
        self._cancel_event = None
        self._stream_text = ""
        self._stream_reasoning = ""
        self._stream_view = None
        self._speed.reset()
        self._update_send_button()
        self._set_bubble_actions_sensitive(True)
        self._sync_empty_state()
        self.request_resize()

    def reset(self):
        self.cancel()
        self.messages = []
        self._bubble_data = []
        self._stream_text = ""
        self._stream_reasoning = ""
        self._stream_view = None
        child = self._chat_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._chat_list.remove(child)
            child = next_child
        self._sync_empty_state()
        self.request_resize()

    def request_resize(self):
        if self._on_resize_cb:
            self._on_resize_cb(self)

    def cancel_pending_refreshes(self):
        self._cancel_markdown_refresh()

    def grab_input_focus(self):
        if hasattr(self, "_input"):
            self._input.grab_focus()

    def set_content_height_limit(self, height):
        """Budget the transcript after the attachment and composer."""
        width = self.get_width() if self.get_width() > 1 else 680
        chrome = sum(
            child.measure(Gtk.Orientation.VERTICAL, width)[1]
            for child in (self._attachment, self._composer)
        )
        limit = max(60, height - chrome)
        self._scroll.set_min_content_height(min(120, limit))
        self._scroll.set_max_content_height(limit)

    def set_attachment(self, widget):
        child = self._attachment.get_first_child()
        while child is not None:
            sibling = child.get_next_sibling()
            self._attachment.remove(child)
            child = sibling
        if widget is not None:
            self._attachment.append(widget)

    # -- ui building --

    def _build_ui(self):
        self._attachment = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(self._attachment)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_has_frame(False)
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_propagate_natural_height(True)
        self._scroll.set_min_content_height(120)
        self._scroll.set_max_content_height(400)
        self._scroll.set_hexpand(True)
        self._scroll.set_vexpand(True)

        self._chat_list = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12
        )
        self._chat_list.set_css_classes(["chat-transcript"])
        self._chat_list.set_hexpand(True)
        self._chat_list.set_valign(Gtk.Align.START)
        self._transcript = Gtk.Stack()
        self._transcript.set_hhomogeneous(False)
        self._transcript.set_vhomogeneous(False)
        self._transcript.add_named(
            empty_state("chat-symbolic", CHAT_EMPTY_TITLE, CHAT_EMPTY_HINT),
            "empty",
        )
        self._transcript.add_named(self._chat_list, "messages")
        self._transcript.set_visible_child_name("empty")
        self._scroll.set_child(self._transcript)

        self.append(self._scroll)
        self._build_composer()
        self._update_send_button()
        self._sync_empty_state()

    def _build_composer(self):
        """A single card holds input and its (secondary) settings.

        Keeping model/thinking/context in the composer instead of a full-width
        toolbar above the transcript removes a whole bar of chrome and makes
        clear that those controls belong to the next message, not the page.
        """
        composer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        composer.set_css_classes(["chat-composer"])
        self._composer = composer

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.set_css_classes(["composer-card"])

        scrolled_input = Gtk.ScrolledWindow()
        scrolled_input.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_input.set_min_content_height(34)
        scrolled_input.set_max_content_height(120)
        scrolled_input.set_propagate_natural_height(True)
        scrolled_input.set_hexpand(True)
        scrolled_input.set_focusable(False)

        self._input = Gtk.TextView()
        self._input.set_css_classes(["chat-input-view"])
        self._input.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._input.set_accepts_tab(False)

        chat_key_ctrl = Gtk.EventControllerKey.new()
        chat_key_ctrl.connect("key-pressed", self._on_input_key)
        self._input.add_controller(chat_key_ctrl)

        self._input.get_buffer().connect("changed", self._on_input_changed)

        scrolled_input.set_child(self._input)
        card.append(attach_placeholder(scrolled_input, self._input, CHAT_PLACEHOLDER))

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        tools.set_hexpand(True)

        self._model_dropdown = model_dropdown(
            self._model_choices, self._model, max_chars=16
        )
        self._model_dropdown.connect("notify::selected", self._on_model_changed)
        tools.append(self._model_dropdown)

        self._thinking_check = Gtk.CheckButton(label=BTN_THINKING)
        self._thinking_check.set_css_classes(["thinking-toggle"])
        self._thinking_check.set_active(self._thinking)
        self._thinking_check.set_tooltip_text(TOOLTIP_THINKING)
        self._thinking_check.connect("toggled", self._on_thinking_toggled)
        if self._show_thinking:
            tools.append(self._thinking_check)

        self._context_btn = Gtk.Button(label=BTN_CONTEXT)
        self._context_btn.set_css_classes(["chip-toggle"])
        self._context_btn.connect("clicked", self._on_context_toggle)
        self._update_context_button()
        tools.append(self._context_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        tools.append(spacer)

        speed_label = Gtk.Label(label="")
        speed_label.set_css_classes(["speed-label"])
        speed_label.set_ellipsize(Pango.EllipsizeMode.END)
        speed_label.set_max_width_chars(14)
        speed_label.set_visible(False)
        speed_label.set_valign(Gtk.Align.CENTER)
        tools.append(speed_label)
        self._speed.set_label(speed_label)

        self._clear_btn = icon_button(
            "trash-symbolic", TOOLTIP_CLEAR, css_classes=("mini-btn",), icon_size=13
        )
        self._clear_btn.connect("clicked", self._on_clear_click)
        tools.append(self._clear_btn)

        self._send_btn = Gtk.Button(label=BTN_SEND)
        self._send_btn.set_css_classes(["chat-send"])
        self._send_btn.set_valign(Gtk.Align.CENTER)
        self._send_btn.set_tooltip_text(CHAT_INPUT_HINT)
        self._send_btn.connect("clicked", lambda b: self._on_send())
        tools.append(self._send_btn)

        card.append(tools)
        composer.append(card)
        self.append(composer)

    # -- settings --

    def _selected_model(self, dropdown):
        index = dropdown.get_selected()
        if index >= len(self._model_choices):
            return self._model_choices[0] if self._model_choices else ""
        return self._model_choices[index]

    def _select_model(self, dropdown, model):
        try:
            index = self._model_choices.index(model)
        except ValueError:
            index = 0
        dropdown.set_selected(index)

    def _on_model_changed(self, dropdown, param):
        self._model = self._selected_model(dropdown)
        self._handle_settings_change()

    def _on_thinking_toggled(self, check):
        self._thinking = check.get_active()
        self._handle_settings_change()

    def _on_context_toggle(self, btn):
        self._include_context = not self._include_context
        self._update_context_button()
        self._handle_settings_change()

    def _on_clear_click(self, btn):
        self.reset()
        if self._on_clear_context_cb:
            self._on_clear_context_cb(self)

    def _update_context_button(self):
        if hasattr(self, "_context_btn"):
            self._context_btn.set_label(BTN_CONTEXT)
            self._context_btn.set_tooltip_text(
                f"{BTN_WITH_CONTEXT if self._include_context else BTN_NO_CONTEXT}（X）"
            )
            if self._include_context:
                self._context_btn.add_css_class("context-active")
            else:
                self._context_btn.remove_css_class("context-active")

    def _handle_settings_change(self):
        if self._on_settings_changed_cb:
            self._on_settings_changed_cb(self)
        if self._loading:
            self.cancel()

    def _remove_stream_bubble(self):
        if not self._bubble_data:
            return
        last = self._bubble_data[-1]
        if not last.get("is_stream"):
            return
        self._chat_list.remove(last["row"])
        self._bubble_data.pop()
        self._stream_view = None

    # -- send / regenerate / edit --

    def _on_send(self):
        if self._loading:
            self.cancel()
            return
        buf = self._input.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, False).strip()
        if not text:
            return
        buf.set_text("")
        self.messages.append(ChatMessage("user", text))
        self._append_bubble("user", text)
        self._request_response()

    def _request_response(self):
        if not self.messages:
            return
        last = self.messages[-1]
        if last.role != "user":
            return
        settings = self.current_settings()
        messages_before = [m.to_dict() for m in self.messages[:-1]]
        if self._on_request_cb:
            self._on_request_cb(self, messages_before, last.content, settings)

    def _on_regenerate(self, btn, index):
        if self._loading:
            return
        self.cancel()
        self._truncate_after(index)
        self._request_response()

    def _on_edit_message(self, btn, index):
        if self._loading:
            return
        self._enter_edit_mode(index)

    def _on_copy_message(self, btn, index):
        if index >= len(self.messages):
            return
        text = self.messages[index].content

        threading.Thread(target=lambda: copy_text(text), daemon=True).start()

        btn.set_label(BTN_COPIED_MSG)
        btn.set_sensitive(False)
        btn.add_css_class("copied")

        def reset_btn():
            # 按钮可能已随气泡/面板销毁
            if btn.get_root() is None:
                return False
            btn.remove_css_class("copied")
            btn.set_sensitive(True)
            btn.set_label(BTN_COPY_MSG)
            return False

        GLib.timeout_add_seconds(1, reset_btn)

    # -- edit mode --

    def _enter_edit_mode(self, index):
        data = self._bubble_data[index]
        original_text = self.messages[index].content

        data["readonly_view"].set_visible(False)
        data["action_box"].set_visible(False)

        edit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        edit_box.set_hexpand(True)

        edit_sw = Gtk.ScrolledWindow()
        edit_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        edit_sw.set_min_content_height(36)
        edit_sw.set_max_content_height(100)
        edit_sw.set_propagate_natural_height(True)
        edit_sw.set_propagate_natural_width(True)
        edit_sw.set_max_content_width(CHAT_USER_BUBBLE_MAX_WIDTH)
        edit_sw.set_hexpand(True)
        edit_sw.set_css_classes(["chat-bubble-edit-sw"])

        edit_view = AutoHeightTextView(
            original_text, ["chat-bubble-edit-view"],
            max_width=CHAT_USER_BUBBLE_MAX_WIDTH,
            on_resize=lambda _view: self.request_resize(),
        )
        edit_view.set_editable(True)
        edit_view.set_cursor_visible(True)

        edit_view.get_buffer().connect("changed", lambda buf: self.request_resize())

        edit_key_ctrl = Gtk.EventControllerKey.new()
        edit_key_ctrl.connect("key-pressed", self._on_edit_key, index)
        edit_view.add_controller(edit_key_ctrl)

        edit_sw.set_child(edit_view)
        edit_box.append(edit_sw)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_row.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=BTN_CANCEL)
        cancel_btn.set_css_classes(["chat-bubble-action-btn"])
        cancel_btn.connect("clicked", self._on_edit_cancel, index)
        btn_row.append(cancel_btn)

        confirm_btn = Gtk.Button(label=BTN_CONFIRM_EDIT)
        confirm_btn.set_css_classes(["chat-bubble-action-btn"])
        confirm_btn.connect("clicked", self._on_edit_confirm, index)
        btn_row.append(confirm_btn)

        edit_box.append(btn_row)
        data["content_vbox"].append(edit_box)

        data["edit_box"] = edit_box
        data["edit_view"] = edit_view
        edit_view.grab_focus()

    def _exit_edit_mode(self, index):
        data = self._bubble_data[index]
        edit_box = data.get("edit_box")
        if edit_box is not None:
            parent = edit_box.get_parent()
            if parent is not None:
                parent.remove(edit_box)
            data["edit_box"] = None
            data["edit_view"] = None
        data["readonly_view"].set_visible(True)
        data["action_box"].set_visible(True)
        self.request_resize()

    def _on_edit_confirm(self, btn, index):
        data = self._bubble_data[index]
        buf = data["edit_view"].get_buffer()
        new_text = buf.get_text(
            buf.get_start_iter(), buf.get_end_iter(), False
        ).strip()
        if not new_text:
            return

        self.cancel()
        self.messages[index] = ChatMessage("user", new_text)
        self._truncate_after(index + 1)

        data["readonly_view"].set_plain_text(new_text)
        self._exit_edit_mode(index)
        self._request_response()

    def _on_edit_cancel(self, btn, index):
        self._exit_edit_mode(index)

    def _on_edit_key(self, controller, keyval, keycode, state, index):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.SHIFT_MASK:
                return False
            self._on_edit_confirm(controller.get_widget(), index)
            return True
        if keyval == Gdk.KEY_Escape:
            self._on_edit_cancel(controller.get_widget(), index)
            return True
        return False

    # -- input --

    def _on_input_key(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & (
                Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK
            ):
                return False
            self._on_send()
            return True
        return False

    def _on_input_changed(self, buf):
        self._update_send_button()
        self.request_resize()

    def _update_send_button(self):
        if not hasattr(self, "_send_btn"):
            return
        buf = self._input.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        self._send_btn.set_label(BTN_STOP if self._loading else BTN_SEND)
        self._send_btn.set_sensitive(self._loading or bool(text))
        if self._loading:
            self._send_btn.add_css_class("stop")
        else:
            self._send_btn.remove_css_class("stop")

    def _sync_empty_state(self):
        has_messages = bool(self._bubble_data)
        self._transcript.set_visible_child_name("messages" if has_messages else "empty")
        if hasattr(self, "_clear_btn"):
            self._clear_btn.set_visible(has_messages)

    # -- bubbles --

    def _append_bubble(self, role, text, index=None):
        if index is None:
            index = len(self._bubble_data)

        view = AutoHeightTextView(
            text,
            ["message-text"],
            min_height=20,
            markdown=(role != "user"),
            max_width=(
                CHAT_BUBBLE_MAX_WIDTH if role == "assistant" else CHAT_USER_BUBBLE_MAX_WIDTH
            ),
            on_resize=lambda _v: self.request_resize(),
        )
        view.set_justification(Gtk.Justification.LEFT)

        content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_vbox.set_hexpand(True)
        content_vbox.set_valign(Gtk.Align.START)

        thinking_container = None
        thinking_view = None

        if role == "assistant":
            thinking_container = Gtk.Expander.new(CHAT_REASONING_TITLE)
            thinking_container.set_css_classes(["chat-thinking-expander"])
            thinking_container.set_expanded(True)
            thinking_container.set_visible(False)
            thinking_container.set_hexpand(True)
            thinking_container.set_halign(Gtk.Align.FILL)

            # 思维链不设固定最大宽：跟随气泡实际宽度(hexpand)，避免其
            # 最小宽度把整个气泡撑宽、进而让正文多算出多余高度
            thinking_view = AutoHeightTextView(
                "",
                ["chat-bubble-thinking-text"],
                min_height=20,
                on_resize=lambda _v: self.request_resize(),
            )
            thinking_view.set_hexpand(True)
            thinking_container.set_child(thinking_view)
            content_vbox.append(thinking_container)

        content_vbox.append(view)

        action_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=4
        )
        action_box.set_css_classes(["chat-bubble-actions"])

        regenerate_btn = None
        edit_btn = None
        copy_btn = None

        if role == "assistant":
            regenerate_btn = Gtk.Button(label=BTN_REGENERATE)
            regenerate_btn.set_css_classes(["chat-bubble-action-btn"])
            regenerate_btn.connect("clicked", self._on_regenerate, index)
            regenerate_btn.set_sensitive(not self._loading)
            action_box.append(regenerate_btn)

            copy_btn = Gtk.Button(label=BTN_COPY_MSG)
            copy_btn.set_css_classes(["chat-bubble-action-btn"])
            copy_btn.connect("clicked", self._on_copy_message, index)
            copy_btn.set_sensitive(not self._loading)
            action_box.append(copy_btn)
        elif role == "user":
            edit_btn = Gtk.Button(label=BTN_EDIT_MSG)
            edit_btn.set_css_classes(["chat-bubble-action-btn"])
            edit_btn.connect("clicked", self._on_edit_message, index)
            edit_btn.set_sensitive(not self._loading)
            action_box.append(edit_btn)

        content_vbox.append(action_box)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.set_css_classes(["chat-row"])
        row.set_hexpand(True)
        row.set_valign(Gtk.Align.START)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)

        bubble = Gtk.Box()
        bubble.set_css_classes([
            "chat-bubble-wrap", "chat-bubble-user" if role == "user" else "chat-bubble-ai"
        ])
        bubble.set_valign(Gtk.Align.START)
        bubble.set_hexpand(False)
        bubble.append(content_vbox)

        if role == "user":
            row.append(spacer)
            row.append(bubble)
        else:
            row.append(bubble)
            row.append(spacer)

        self._chat_list.append(row)
        if role == "user":
            restore_after_relayout(self._scroll.get_vadjustment(), 0, at_bottom=True)

        bubble_data = {
            "row": row,
            "bubble": bubble,
            "content_vbox": content_vbox,
            "readonly_view": view,
            "action_box": action_box,
            "regenerate_btn": regenerate_btn,
            "edit_btn": edit_btn,
            "copy_btn": copy_btn,
            "thinking_container": thinking_container,
            "thinking_view": thinking_view,
            "edit_box": None,
            "is_stream": False,
        }
        if index < len(self._bubble_data):
            self._bubble_data[index] = bubble_data
        else:
            self._bubble_data.append(bubble_data)

        self._sync_empty_state()
        self.request_resize()
        return view, row

    def _set_bubble_actions_sensitive(self, sensitive):
        for data in self._bubble_data:
            for key in ("regenerate_btn", "edit_btn", "copy_btn"):
                btn = data.get(key)
                if btn is not None:
                    btn.set_sensitive(sensitive)

    def _truncate_after(self, keep_count):
        self.messages = self.messages[:keep_count]
        self._bubble_data = self._bubble_data[:keep_count]
        child = self._chat_list.get_first_child()
        row_index = 0
        to_remove = []
        while child is not None:
            next_child = child.get_next_sibling()
            if row_index >= keep_count:
                to_remove.append(child)
            child = next_child
            row_index += 1
        for row in to_remove:
            self._chat_list.remove(row)
        self._sync_empty_state()
        self.request_resize()

    # -- markdown refresh --

    def _schedule_markdown_refresh(self):
        if self._markdown_refresh_id:
            return
        self._markdown_refresh_id = GLib.timeout_add(
            STREAM_MARKDOWN_REFRESH_DELAY_MS, self._do_markdown_refresh
        )

    def _cancel_markdown_refresh(self):
        if self._markdown_refresh_id:
            GLib.source_remove(self._markdown_refresh_id)
            self._markdown_refresh_id = None

    def _do_markdown_refresh(self):
        self._markdown_refresh_id = None
        if self.get_parent() is None:
            return False
        if self._stream_view is not None:
            view = self._stream_view
            text = self._stream_text
            render_preserving_scroll(
                self._scroll, lambda: view.set_markdown_text(text)
            )
        return False
