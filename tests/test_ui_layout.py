"""Opt-in GTK integration tests. No API credentials or network are used.

Run with POP_TRANSLATE_TEST_UI=1 python -m pytest tests/test_ui_layout.py.
A GTK display is required; GDK_BACKEND=broadway works for a virtual display.
"""

import os
import runpy
import subprocess
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("POP_TRANSLATE_TEST_UI") != "1",
    reason="Set POP_TRANSLATE_TEST_UI=1 to run native GTK layout checks",
)

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
except ValueError:
    pytest.skip("GTK4 introspection is not installed", allow_module_level=True)
from gi.repository import GdkPixbuf, GLib, Gtk

from pop_translate.config import Config
from pop_translate.i18n import BTN_STOP, CHAT_THINKING
from pop_translate.ui.chat_panel import ChatPanel
from pop_translate.ui.setup_dialog import SetupDialog
from pop_translate.ui.widgets import load_styles
from pop_translate.ui.window import TranslateWindow


def settle(seconds=0.6):
    context = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.002)


def buffer_text(view):
    buf = view.get_buffer()
    return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)


@pytest.fixture(scope="module")
def app():
    if not Gtk.init_check():
        pytest.skip("No GTK display available")
    load_styles()
    application = Gtk.Application(application_id="io.poptranslate.LayoutTests")
    application.register(None)
    return application


@pytest.fixture
def panel(app):
    window = Gtk.Window()
    window.set_default_size(680, 420)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    root.set_css_classes(["translate-window"])
    # Layout at a fixed inner width so tiling compositors cannot change it.
    root.set_halign(Gtk.Align.CENTER)
    root.set_valign(Gtk.Align.START)
    root.set_size_request(680, -1)
    chat = ChatPanel(("test-model",), "test-model")
    root.append(chat)
    window.set_child(root)
    window.present()
    settle()
    yield window, chat
    chat.cancel()
    window.destroy()
    settle(.04)


@pytest.fixture
def window(app, monkeypatch):
    # Even a mistaken request in a UI test must never reach a real service.
    for name in ("translate_stream", "explain_stream", "vision_stream", "chat_stream", "vision_chat_stream"):
        monkeypatch.setattr(
            f"pop_translate.ui.window.{name}", lambda *args, **kwargs: iter(("测试回复",))
        )
    result = TranslateWindow(app, "Good design is clear.", Config(), None, default_tab="chat")
    result._stop_autoclose_timer()
    # Measure the popup at its real design width even on a tiling compositor.
    result.outer.set_halign(Gtk.Align.CENTER)
    result.outer.set_valign(Gtk.Align.START)
    result.outer.set_size_request(680, -1)
    result.present()
    settle()
    yield result
    result._cancel_active_requests()
    result._stop_autoclose_timer()
    if result._resize_timeout_id:
        GLib.source_remove(result._resize_timeout_id)
        result._resize_timeout_id = None
    result._vision_image_path = None
    result.destroy()
    settle(.04)


def finish_reply(panel, text):
    event = threading.Event()
    panel.start_stream(event)
    panel.append_chunk(event, text)
    panel.finish_stream(event, text)
    settle()


def test_short_message_does_not_accumulate_padding(panel):
    _, chat = panel
    chat.append_user_message("请分析这张截图。")
    settle()
    data = chat._bubble_data[0]
    view = data["readonly_view"]
    initial_height = data["bubble"].get_height()
    for _ in range(8):
        view.set_plain_text("请分析这张截图。")
        view._refresh_size()
        settle(.025)
    assert view.get_size_request().height == -1
    assert view.get_height() < 60
    assert data["bubble"].get_height() <= initial_height + 2
    assert data["row"].get_height() < 120


def test_long_text_reflows_and_shrinks_back(panel):
    host, chat = panel
    chat.append_user_message("一段会随着窗口宽度正确换行的内容。" * 28)
    settle()
    view = chat._bubble_data[0]["readonly_view"]
    wide_width, wide_height = view.get_width(), view.get_height()
    host.get_child().set_size_request(480, -1)
    settle(.6)
    assert chat.get_width() <= 482
    assert view.get_width() < wide_width
    assert view.get_height() >= wide_height
    end = view.get_iter_location(view.get_buffer().get_end_iter())
    assert end.y + end.height <= view.get_height() + 2
    view.set_plain_text("简短内容")
    settle(.6)
    assert view.get_height() < 60


def test_markdown_height_includes_heading_and_wrapped_code(panel):
    host, chat = panel
    host.get_child().set_size_request(480, -1)
    settle(.3)
    chat.append_user_message("说明")
    finish_reply(chat, "## 标题\n\n**重点**与普通文字。\n\n```python\n" + "print('example'); " * 24 + "\n```")
    view = chat._bubble_data[-1]["readonly_view"]
    end = view.get_iter_location(view.get_buffer().get_end_iter())
    assert end.y + end.height <= view.get_height() + 2
    assert view.get_width() < chat.get_width() - 16


def test_pending_reply_has_visible_status_and_stop_action(panel):
    _, chat = panel
    chat.append_user_message("问题")
    event = threading.Event()
    chat.start_stream(event)
    assert buffer_text(chat._stream_view) == CHAT_THINKING
    assert chat._send_btn.get_label() == BTN_STOP
    assert chat._send_btn.get_sensitive()
    assert not chat._bubble_data[-1]["action_box"].get_visible()
    chat._on_send()
    assert event.is_set()
    assert not chat.loading
    assert len(chat._bubble_data) == len(chat.messages) == 1


def test_completed_reply_survives_cancel_and_settings_change(panel):
    _, chat = panel
    chat.append_user_message("问题")
    finish_reply(chat, "已经完成的回复")
    chat.cancel()
    chat.toggle_context()
    assert len(chat._bubble_data) == len(chat.messages) == 2
    assert not chat._bubble_data[-1]["is_stream"]
    assert buffer_text(chat._bubble_data[-1]["readonly_view"]) == "已经完成的回复"


def test_empty_state_returns_after_clear(panel):
    _, chat = panel
    assert chat._transcript.get_visible_child_name() == "empty"
    chat.append_user_message("问题")
    assert chat._transcript.get_visible_child_name() == "messages"
    chat.reset()
    assert chat._transcript.get_visible_child_name() == "empty"
    assert chat._chat_list.get_first_child() is None
    assert not chat._send_btn.get_sensitive()


def test_inline_edit_fits_narrow_window(panel):
    host, chat = panel
    host.get_child().set_size_request(480, -1)
    settle(.3)
    chat.append_user_message("原文编辑需要在窄窗口里保持足够的输入空间。" * 6)
    settle()
    chat._enter_edit_mode(0)
    settle()
    data = chat._bubble_data[0]
    assert data["edit_view"].get_editable()
    assert 180 < data["edit_box"].get_width() < chat.get_width() - 30
    assert data["edit_view"].get_width() <= data["edit_box"].get_width()
    chat._on_edit_cancel(None, 0)
    assert data["readonly_view"].get_visible()
    assert data["edit_box"] is None


def test_stream_updates_keep_short_user_bubble_compact(panel):
    _, chat = panel
    chat.append_user_message("请解释")
    settle()
    height = chat._bubble_data[0]["row"].get_height()
    event = threading.Event()
    chat.start_stream(event)
    for chunk in ("## 流式回复\n\n", "这是一段逐步生成的内容。" * 20, "\n\n最后一行。"):
        chat.append_chunk(event, chunk)
        settle(.23)
    result = chat.stream_text
    chat.finish_stream(event, result)
    settle()
    assert chat._bubble_data[0]["row"].get_height() == height
    view = chat._bubble_data[-1]["readonly_view"]
    end = view.get_iter_location(view.get_buffer().get_end_iter())
    assert end.y + end.height <= view.get_height() + 2
    assert "最后一行。" in buffer_text(view)


def test_result_page_is_compact_with_fixed_toolbar(window):
    window.translated = "好的设计是清晰的。"
    window._switch_tab("translate")
    settle(.3)
    assert window.content_area.get_size_request().height == -1
    assert window._translate_result_view.get_size_request().height == -1
    assert not window._translate_result_view.get_vexpand()
    assert window._page_toolbar is window._status_bar
    assert window._status_bar.get_parent() is window.outer
    assert window._status_bar.get_visible()
    assert window._content_scroll.get_parent() is window.content_area
    assert window.get_default_size().height < 500


def test_long_result_scrolls_inside_height_budget(window):
    window.explanation = "## 一段解释\n\n" + "一段很长的说明文字。\n\n" * 100
    window._switch_tab("explain")
    settle(.4)
    adjustment = window._content_scroll.get_vadjustment()
    assert adjustment.get_upper() > adjustment.get_page_size()
    assert window.get_default_size().height <= window._window_height_limit()
    assert window._page_toolbar is window._status_bar


def test_vision_uses_compact_attachment_and_one_transcript(window, tmp_path):
    path = str(tmp_path / "capture.png")
    image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 800, 600)
    image.fill(0xCCDDEEFF)
    image.savev(path, "png", [], [])
    window._vision_image_path = path
    chat = window._ensure_vision_chat_panel()
    chat.append_user_message("请分析这张截图。")
    finish_reply(chat, "这是一张测试图片。")
    window._switch_tab("vision")
    settle(.3)
    assert chat.get_parent() is window.content_area
    assert chat._attachment.get_height() <= 90
    assert chat._scroll.get_parent() is chat
    assert chat._bubble_data[0]["row"].get_height() < 120
    assert window.get_default_size().height <= window._window_height_limit()


def test_vision_hotkey_launch_carries_capture_and_starts_analysis(app, monkeypatch):
    """Exercise the python -m entry point without capturing the desktop or using an API."""
    windows = []
    captures = []
    requests = []
    observed = {}
    response = "截图已自动识别。"
    original_window = TranslateWindow

    class RecordedWindow(original_window):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            windows.append(self)

    def load_test_config(config):
        config.api_key = "test-key"

    def run_capture(command, *args, **kwargs):
        if command[0] == "slurp":
            return subprocess.CompletedProcess(command, 0, stdout="0,0 32x20\n")
        if command[0] == "grim":
            path = command[-1]
            image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 32, 20)
            image.fill(0xCCDDEEFF)
            image.savev(path, "png", [], [])
            captures.append(path)
            return subprocess.CompletedProcess(command, 0)
        raise AssertionError(f"Unexpected external command: {command[0]}")

    def analyze_capture(path, config, **kwargs):
        assert os.path.getsize(path) > 0
        requests.append((path, kwargs["model"] or config.vision_model))
        yield response

    monkeypatch.setattr(Config, "load", load_test_config)
    monkeypatch.setattr("pop_translate.history.HistoryDB", lambda: None)
    monkeypatch.setattr("pop_translate.clipboard._is_wayland", lambda: True)
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(subprocess, "run", run_capture)
    monkeypatch.setattr("pop_translate.ui.window.TranslateWindow", RecordedWindow)
    monkeypatch.setattr("pop_translate.ui.window.vision_stream", analyze_capture)
    monkeypatch.setattr(sys, "argv", ["pop-translate", "--vision"])
    deadline = time.monotonic() + 3

    def finish_launch():
        if not windows:
            return True
        window = windows[0]
        if not window.vision_result and window._vision_image_path and time.monotonic() < deadline:
            return True
        observed.update(
            image=window._vision_image_path,
            tab=window._current_tab,
            result=window.vision_result,
            messages=list(window._vision_chat_panel.messages) if window._vision_chat_panel else [],
        )
        window.close()
        return False

    source_id = GLib.timeout_add(10, finish_launch)
    try:
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("pop_translate", run_name="__main__", alter_sys=True)
        assert exit_info.value.code == 0
        assert len(captures) == 1
        assert observed["image"] == captures[0]
        assert observed["tab"] == "vision"
        assert requests == [(captures[0], "deepseek-flash")]
        assert observed["result"] == response
        assert len(observed["messages"]) == 2
        assert not os.path.exists(captures[0])
    finally:
        if GLib.MainContext.default().find_source_by_id(source_id):
            GLib.source_remove(source_id)
        for window in windows:
            window._cancel_active_requests()
            window._stop_autoclose_timer()
            window.destroy()
        for path in captures:
            if os.path.exists(path):
                os.remove(path)
        settle(.04)


def test_repeated_tab_switches_keep_messages_compact(window):
    chat = window._chat_panel
    chat.append_user_message("短消息")
    finish_reply(chat, "简短回复")
    window.translated = "翻译结果"
    window.explanation = "解释结果"
    for tab in ("translate", "explain", "vision", "chat") * 3:
        window._switch_tab(tab)
        settle(.05)
    settle(.2)
    assert len(chat.messages) == len(chat._bubble_data) == 2
    assert all(data["readonly_view"].get_height() < 60 for data in chat._bubble_data)
    assert chat._chat_list.get_valign() == Gtk.Align.START


def test_main_pages_fit_a_narrow_window(window):
    window.translated = "翻译内容"
    window.explanation = "## 标题\n\n解释内容"
    window.outer.set_size_request(480, -1)
    settle(.6)
    for tab in ("translate", "explain", "chat", "vision"):
        window._switch_tab(tab)
        settle(.3)
        assert window.outer.get_width() <= 482
        assert window.get_default_size().height <= window._window_height_limit()


def test_long_model_name_does_not_force_wide_toolbar(app):
    name = "provider/this-is-a-very-long-model-name-with-an-experimental-version-2026"
    chat = ChatPanel((name,), name)
    host = Gtk.Window()
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    root.set_halign(Gtk.Align.CENTER)
    root.set_valign(Gtk.Align.START)
    root.set_size_request(480, -1)
    root.append(chat)
    host.set_child(root)
    host.set_default_size(680, 360)
    host.present()
    settle(.4)
    try:
        assert chat.get_width() <= 482
        assert chat._model_dropdown.get_tooltip_text() == name
    finally:
        chat.cancel()
        host.destroy()


def test_setup_validation_and_password_visibility(app, monkeypatch):
    config = Config()
    saved = []
    monkeypatch.setattr(config, "save", lambda: saved.append(True))
    dialog = SetupDialog(config, lambda: None)
    dialog.present()
    settle()
    try:
        dialog._on_save(None)
        assert not saved
        assert dialog.error_label.get_opacity() == 1
        dialog.key_entry.set_text("test-key")
        dialog.timeout_entry.set_text("invalid")
        dialog._on_save(None)
        assert not saved
        assert config.api_key == ""
        dialog._toggle_key_visibility(dialog.key_entry, Gtk.EntryIconPosition.SECONDARY)
        assert dialog.key_entry.get_visibility()
        dialog.timeout_entry.set_text("60")
        dialog._on_save(None)
        assert saved == [True]
    finally:
        dialog.destroy()


def test_header_and_footer_stay_compact(window):
    window.translated = "好的设计是清晰的。"
    window._switch_tab("translate")
    settle(.3)
    assert not hasattr(window, "_shortcut_hint_label")
    assert not hasattr(window, "tab_bar")
    assert window.header.get_height() <= 48
    assert window._status_bar.get_height() <= 42
    assert window.header.get_height() + window._status_bar.get_height() < 90


def test_status_bar_is_hidden_on_chat_and_vision(window):
    for tab in ("translate", "explain"):
        window._switch_tab(tab)
        settle(.15)
        assert window._status_bar.get_visible()
    for tab in ("chat", "vision"):
        window._switch_tab(tab)
        settle(.15)
        assert not window._status_bar.get_visible()
    window._switch_tab("translate")
    settle(.2)
    assert window._status_bar.get_visible()


def test_source_preview_clamps_then_expands(window):
    window._cancel_translation_request()
    window.text = ("这是一段很长的原文，用来验证折叠与展开行为。" * 20)
    window.translated = "设计不只是它的外观与触感。"
    window._switch_tab("translate")
    settle(.3)
    assert window._source_label.get_lines() == 3
    assert window._source_toggle_btn is not None
    collapsed = window._source_label.get_height()
    window._on_toggle_source(None)
    settle(.3)
    assert window._source_label.get_lines() == -1
    assert window._source_label.get_height() > collapsed
    assert window._source_toggle_btn.get_label() == "收起"


def test_translation_copy_action_appears_with_result(window):
    window._cancel_translation_request()
    window.translated = ""
    window._translate_loading = False
    window._translate_error = None
    window.text = "Hello"
    window._current_tab = "translate"
    window._clear_content()
    window._show_result_page("translate")
    settle(.25)
    assert window._translate_copy_btn is None or not window._translate_copy_btn.get_visible()
    window.translated = "你好"
    window._clear_content()
    window._show_result_page("translate")
    settle(.3)
    assert window._translate_copy_btn is not None
    assert window._translate_copy_btn.get_visible()
    assert window._translate_copy_btn.get_sensitive()


def test_explanation_copy_action_appears_with_result(window):
    window._cancel_explain_request()
    window.explanation = "## 解释\n\n一段说明。"
    window._explain_loading = False
    window._explain_error = None
    window._current_tab = "explain"
    window._clear_content()
    window._show_result_page("explain")
    settle(.3)
    assert window._explain_copy_btn is not None
    assert window._explain_copy_btn.get_visible()
    assert window._explain_copy_btn.get_sensitive()


def test_help_button_opens_shortcut_popover(window):
    assert window.header is not None
    popovers = []
    child = window.header.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Button) and child.get_tooltip_text() == "键盘快捷键":
            popovers.append(child)
        child = child.get_next_sibling()
    assert popovers
    button = popovers[0]
    button.emit("clicked")
    settle(.1)
    assert button.get_parent() is window.header
    assert window.help_popover is not None
    assert window.help_popover.get_child() is not None
