import re
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gdk, Gtk, Pango

from ..api import StreamEvent
from ..clipboard import copy_text
from ..i18n import (
    BTN_CANCEL,
    BTN_CONFIRM_EDIT,
    BTN_EDIT_MSG,
    BTN_REGENERATE,
    BTN_SEND,
    BTN_THINKING,
    BTN_WITH_CONTEXT,
    BTN_NO_CONTEXT,
    CHAT_THINKING,
    SPEED_LABEL,
    BTN_COPY_MSG,
    BTN_COPIED_MSG,
    BTN_CLEAR_CONTENT,
)

CHAT_BUBBLE_MIN_WIDTH = 96
CHAT_BUBBLE_MAX_WIDTH = 480
STREAM_MARKDOWN_REFRESH_DELAY_MS = 200


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
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_hexpand(True)

        self._model_choices = tuple(model_choices)
        self._model = initial_model
        self._thinking = initial_thinking
        self._include_context = initial_include_context

        self.messages = []

        self._bubble_data = []
        self._loading = False
        self._cancel_event = None
        self._stream_text = ""
        self._stream_view = None

        self._speed_stats = None
        self._speed_label = None

        self._markdown_refresh_id = None

        self._text_min_heights = {}
        self._text_widths = {}
        self._text_min_widths = {}

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

    def start_stream(self, cancel_event):
        self._cancel_event = cancel_event
        self._loading = True
        self._stream_text = ""
        self._stream_reasoning = ""
        self._send_btn.set_sensitive(False)
        self._set_bubble_actions_sensitive(False)
        self._stream_view, _ = self._append_bubble("assistant", "")
        if self._bubble_data:
            last = self._bubble_data[-1]
            last["is_stream"] = True
            if last["thinking_container"] is not None:
                last["thinking_container"].set_expanded(True)
                if self._thinking:
                    last["thinking_container"].set_visible(True)
                    self._set_text_view_text(last["thinking_view"], CHAT_THINKING)
                else:
                    last["thinking_container"].set_visible(False)
        self._start_speed_stats()

    def append_chunk(self, cancel_event, chunk):
        if cancel_event is not self._cancel_event or cancel_event.is_set():
            return
        if not chunk:
            return
        self._record_speed_chunk(chunk)
        if self._bubble_data:
            last = self._bubble_data[-1]
            if last.get("is_stream") and last["thinking_container"] is not None:
                if not self._stream_reasoning:
                    last["thinking_container"].set_visible(False)
        if not self._stream_text:
            self._set_text_view_text(self._stream_view, "")
        self._stream_text += chunk
        self._schedule_markdown_refresh()

    def handle_event(self, cancel_event, event):
        if cancel_event is not self._cancel_event or cancel_event.is_set():
            return
        if event.kind == "usage":
            self._record_speed_usage(event.data)
        elif event.kind == "reasoning":
            if not self._thinking:
                return
            if self._bubble_data:
                last = self._bubble_data[-1]
                if last.get("is_stream") and last["thinking_container"] is not None:
                    if not self._stream_reasoning:
                        self._set_text_view_text(last["thinking_view"], "")
                    self._stream_reasoning += event.text
                    self._set_text_view_text(last["thinking_view"], self._stream_reasoning)
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
        self._cancel_markdown_refresh()
        self._render_markdown_preserving_scroll(
            self._stream_view, result, self._scroll
        )
        self._loading = False
        self._cancel_event = None
        self._send_btn.set_sensitive(True)
        self._set_bubble_actions_sensitive(True)
        self._finish_speed_stats()
        if self._bubble_data:
            last = self._bubble_data[-1]
            if last.get("thinking_container") is not None:
                last["thinking_container"].set_expanded(False)

    def cancel(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_markdown_refresh()
        self._loading = False
        self._cancel_event = None
        self._stream_text = ""
        self._reset_speed_stats()
        self._send_btn.set_sensitive(True)
        self._set_bubble_actions_sensitive(True)

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

    def request_resize(self):
        if self._on_resize_cb:
            self._on_resize_cb(self)

    def cancel_pending_refreshes(self):
        self._cancel_markdown_refresh()

    def grab_input_focus(self):
        if hasattr(self, "_input"):
            self._input.grab_focus()

    # -- ui building --

    def _build_ui(self):
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.set_css_classes(["control-bar", "chat-control-bar"])
        controls.set_hexpand(True)

        self._model_dropdown = Gtk.DropDown.new_from_strings(
            list(self._model_choices)
        )
        self._model_dropdown.set_css_classes(["model-select"])
        self._select_model(self._model_dropdown, self._model)
        self._model_dropdown.connect("notify::selected", self._on_model_changed)
        controls.append(self._model_dropdown)

        self._thinking_check = Gtk.CheckButton(label=BTN_THINKING)
        self._thinking_check.set_css_classes(["thinking-toggle"])
        self._thinking_check.set_active(self._thinking)
        self._thinking_check.connect("toggled", self._on_thinking_toggled)
        controls.append(self._thinking_check)

        self._context_btn = Gtk.Button(
            label=BTN_WITH_CONTEXT if self._include_context else BTN_NO_CONTEXT
        )
        self._context_btn.set_css_classes(["action-btn"])
        self._context_btn.connect("clicked", self._on_context_toggle)
        controls.append(self._context_btn)

        self._clear_btn = Gtk.Button(label=BTN_CLEAR_CONTENT)
        self._clear_btn.set_css_classes(["action-btn"])
        self._clear_btn.connect("clicked", self._on_clear_click)
        controls.append(self._clear_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        controls.append(spacer)

        self._speed_label = Gtk.Label(label="")
        self._speed_label.set_css_classes(["speed-label"])
        self._speed_label.set_halign(Gtk.Align.END)
        self._speed_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._speed_label.set_visible(False)
        controls.append(self._speed_label)

        self.append(controls)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_has_frame(False)
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_propagate_natural_height(True)
        self._scroll.set_min_content_height(200)
        self._scroll.set_max_content_height(480)
        self._scroll.set_hexpand(True)

        self._chat_list = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8
        )
        self._chat_list.set_css_classes(["chat-area"])
        self._chat_list.set_hexpand(True)
        self._scroll.set_child(self._chat_list)

        self.append(self._scroll)

        input_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_bar.set_css_classes(["chat-input-bar"])
        input_bar.set_hexpand(True)

        scrolled_input = Gtk.ScrolledWindow()
        scrolled_input.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_input.set_min_content_height(44)
        scrolled_input.set_max_content_height(100)
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
        input_bar.append(scrolled_input)

        self._send_btn = Gtk.Button(label=BTN_SEND)
        self._send_btn.set_css_classes(["chat-send"])
        self._send_btn.set_sensitive(True)
        self._send_btn.connect("clicked", lambda b: self._on_send())
        input_bar.append(self._send_btn)

        self.append(input_bar)

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
        if self._loading:
            self.cancel()
            self._remove_stream_bubble()

    def _on_clear_click(self, btn):
        self.reset()
        if self._on_clear_context_cb:
            self._on_clear_context_cb(self)

    def _update_context_button(self):
        if hasattr(self, "_context_btn"):
            self._context_btn.set_label(
                BTN_WITH_CONTEXT if self._include_context else BTN_NO_CONTEXT
            )

    def _handle_settings_change(self):
        if self._on_settings_changed_cb:
            self._on_settings_changed_cb(self)
        if not self._loading:
            return
        self.cancel()
        self._remove_stream_bubble()

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

        def worker():
            copy_text(text)

        import threading
        threading.Thread(target=worker, daemon=True).start()

        btn.set_label(BTN_COPIED_MSG)
        btn.set_sensitive(False)
        btn.add_css_class("copied")

        GLib.timeout_add_seconds(
            1,
            lambda: (
                btn.remove_css_class("copied"),
                btn.set_sensitive(True),
                btn.set_label(BTN_COPY_MSG),
                False,
            )[-1],
        )

    # -- edit mode --

    def _enter_edit_mode(self, index):
        data = self._bubble_data[index]
        original_text = self.messages[index].content

        data["readonly_view"].set_visible(False)
        data["action_box"].set_visible(False)

        edit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        edit_box.set_css_classes(["chat-bubble-user", "chat-bubble-editing"])
        edit_box.set_size_request(CHAT_BUBBLE_MAX_WIDTH, -1)

        edit_sw = Gtk.ScrolledWindow()
        edit_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        edit_sw.set_min_content_height(36)
        edit_sw.set_max_content_height(100)
        edit_sw.set_propagate_natural_height(True)
        edit_sw.set_hexpand(True)
        edit_sw.set_css_classes(["chat-bubble-edit-sw"])

        edit_view = Gtk.TextView()
        edit_view.get_buffer().set_text(original_text)
        edit_view.set_css_classes(["chat-bubble-edit-view"])
        edit_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        edit_view.set_accepts_tab(False)

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

        data["readonly_view"].get_buffer().set_text(new_text)
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
        self.request_resize()

    # -- bubbles --

    def _append_bubble(self, role, text, index=None):
        if index is None:
            index = len(self._bubble_data)

        css_classes = (
            ["chat-bubble-user"] if role == "user" else ["chat-bubble-ai"]
        )
        view = self._readonly_text_view(
            text,
            css_classes,
            min_height=40,
            markdown=(role != "user"),
            width=CHAT_BUBBLE_MAX_WIDTH,
        )
        view.set_justification(Gtk.Justification.LEFT)

        content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        thinking_container = None
        thinking_view = None

        if role == "assistant":
            thinking_container = Gtk.Expander.new("思维过程")
            thinking_container.set_css_classes(["chat-thinking-expander"])
            thinking_container.set_expanded(True)
            thinking_container.set_visible(False)

            thinking_view = self._readonly_text_view(
                "",
                ["chat-bubble-thinking-text"],
                min_height=20,
                markdown=False,
                width=CHAT_BUBBLE_MAX_WIDTH - 24,
            )
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

        spacer = Gtk.Box()
        spacer.set_hexpand(True)

        bubble = Gtk.Box()
        bubble.set_css_classes(["chat-bubble-wrap"])
        bubble.set_size_request(CHAT_BUBBLE_MIN_WIDTH, -1)
        bubble.set_hexpand(False)
        bubble.append(content_vbox)

        if role == "user":
            row.append(spacer)
            row.append(bubble)
        else:
            row.append(bubble)
            row.append(spacer)

        self._chat_list.append(row)
        self._scroll_to_bottom()

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

        return view, row

    def _scroll_to_bottom(self):
        def scroll():
            adj = self._scroll.get_vadjustment()
            adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))
            return False

        GLib.idle_add(scroll)

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

    # -- text view helpers --

    def _readonly_text_view(
        self, text, css_classes, min_height=24, markdown=False, width=None
    ):
        view = Gtk.TextView()
        view.set_css_classes(css_classes)
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_accepts_tab(False)
        view.set_hexpand(width is None)
        view.set_vexpand(False)
        view.set_valign(Gtk.Align.START)
        self._text_min_heights[view] = min_height
        self._text_widths[view] = width if width is not None else -1
        if width is not None:
            view.set_size_request(width, -1)
        view.get_buffer().connect(
            "changed", lambda _buf, v=view: self._schedule_text_view_height(v)
        )
        if markdown:
            self._set_text_view_markdown(view, text or "")
        else:
            view.get_buffer().set_text(text or "")
        self._schedule_text_view_height(view)
        return view

    def _set_text_view_text(self, view, text):
        if view is None:
            return
        view.get_buffer().set_text(text or "")
        self._schedule_text_view_height(view)

    def _schedule_text_view_height(self, view):
        GLib.idle_add(self._refresh_text_view_height, view)

    def _refresh_text_view_height(self, view, request_resize=True):
        if view is None or view.get_parent() is None:
            return False
        width = self._text_widths.get(view, -1)
        alloc_w = view.get_allocated_width()
        if alloc_w <= 1:
            if width > 0:
                view.set_size_request(width, -1)
            if request_resize:
                GLib.timeout_add(20, self._refresh_text_view_height, view)
            return False
        min_height = self._text_min_heights.get(view, 24)
        # 用 TextView 在目标宽度下的自然高度(已含 CSS padding / 行距),
        # 直接作为 size_request,避免 iter_location 与实际渲染高度不一致
        # 而把气泡撑出多余空白。
        for_w = alloc_w if alloc_w > 1 else width
        _, natural_h, _, _ = view.measure(Gtk.Orientation.VERTICAL, for_w)
        height = max(min_height, natural_h)
        view.set_size_request(width, height)
        if request_resize:
            self.request_resize()
        return False

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
            buf.create_tag(
                "md_link", underline=Pango.Underline.SINGLE, foreground="#0969da"
            )

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
            r"`([^`]+)`"
            r"|\*\*([^*]+)\*\*"
            r"|\[([^\]]+)\]\([^)]+\)"
            r"|(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)"
        )
        pos = 0
        for match in pattern.finditer(text):
            if match.start() > pos:
                self._insert_tagged(buf, text[pos : match.start()], base_tags)
            if match.group(1) is not None:
                self._insert_tagged(
                    buf, match.group(1), (*base_tags, "md_code")
                )
            elif match.group(2) is not None:
                self._insert_tagged(
                    buf, match.group(2), (*base_tags, "md_bold")
                )
            elif match.group(3) is not None:
                self._insert_tagged(
                    buf, match.group(3), (*base_tags, "md_link")
                )
            elif match.group(4) is not None:
                self._insert_tagged(
                    buf, match.group(4), (*base_tags, "md_italic")
                )
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
                self._insert_markdown_inline(
                    buf, heading.group(1).strip(), ("md_heading",)
                )
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
            self._render_markdown_preserving_scroll(
                self._stream_view, self._stream_text, self._scroll
            )
        return False

    def _render_markdown_preserving_scroll(self, view, text, scrolled):
        if view is None:
            return
        adjustment = scrolled.get_vadjustment() if scrolled is not None else None
        scroll_value = (
            adjustment.get_value() if adjustment is not None else None
        )
        was_at_bottom = (
            self._is_adjustment_at_bottom(adjustment)
            if adjustment is not None
            else False
        )
        self._set_text_view_markdown(view, text)
        self.request_resize()
        if adjustment is not None and scroll_value is not None:
            GLib.timeout_add(
                20,
                self._restore_adjustment_value,
                adjustment,
                scroll_value,
                was_at_bottom,
            )

    def _is_adjustment_at_bottom(self, adjustment):
        if adjustment is None:
            return False
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()
        max_value = max(0, upper - page_size)
        return adjustment.get_value() >= max_value - 2

    def _restore_adjustment_value(self, adjustment, value, scroll_to_bottom=False):
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()
        max_value = max(0, upper - page_size)
        adjustment.set_value(
            max_value if scroll_to_bottom else min(value, max_value)
        )
        return False

    # -- speed stats --

    def _start_speed_stats(self):
        self._speed_stats = {
            "start": time.monotonic(),
            "chars": 0,
            "completion_tokens": None,
            "cached": False,
            "final": False,
        }
        self._refresh_speed_label()

    def _reset_speed_stats(self):
        self._speed_stats = None
        self._refresh_speed_label()

    def _record_speed_chunk(self, chunk):
        stats = self._speed_stats
        if stats is None or stats.get("cached"):
            return
        stats["chars"] += len(chunk)
        self._refresh_speed_label()

    def _record_speed_usage(self, usage):
        stats = self._speed_stats
        if stats is None or not isinstance(usage, dict):
            return
        completion_tokens = usage.get("completion_tokens")
        if isinstance(completion_tokens, int) and completion_tokens > 0:
            stats["completion_tokens"] = completion_tokens

    def _finish_speed_stats(self):
        stats = self._speed_stats
        if stats is None:
            return
        stats["final"] = True
        self._refresh_speed_label()

    def _refresh_speed_label(self):
        if self._speed_label is None:
            return
        stats = self._speed_stats
        if stats is None or stats.get("cached"):
            self._speed_label.set_label("")
            self._speed_label.set_visible(False)
            return
        elapsed = max(0.001, time.monotonic() - stats["start"])
        completion_tokens = stats.get("completion_tokens")
        if stats.get("final") and completion_tokens:
            text = f"{SPEED_LABEL} {completion_tokens / elapsed:.1f} token/s"
        else:
            chars = stats.get("chars", 0)
            if chars <= 0:
                self._speed_label.set_label("")
                self._speed_label.set_visible(False)
                return
            text = f"{SPEED_LABEL} {chars / elapsed:.1f} 字/s"
        self._speed_label.set_label(text)
        self._speed_label.set_visible(True)
