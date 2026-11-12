"""共享 UI 组件：自适应高度 TextView、Markdown 渲染、滚动工具与速度统计。

window.py 与 chat_panel.py 此前各持一份实现且已经行为分叉(高度计算
算法、markdown 细节、滚动恢复时机)，本模块是唯一实现。
"""

import re
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango

from ..i18n import SPEED_LABEL

STREAM_MARKDOWN_REFRESH_DELAY_MS = 200

_MD_INLINE_RE = re.compile(
    r"`([^`]+)`"
    r"|\*\*([^*]+)\*\*"
    r"|\[([^\]]+)\]\(([^)]+)\)"
    r"|(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)"
)
_MD_HEADING_RE = re.compile(r"^\s*(#{1,4})\s+(.+)$")
_MD_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.+)$")
_MD_NUMBERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
_MD_HEADING_SCALE = (1.26, 1.16, 1.09, 1.04)


def open_url_async(url):
    def worker():
        try:
            subprocess.run(
                ["xdg-open", url], capture_output=True, timeout=5, check=False
            )
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


class AutoHeightTextView(Gtk.TextView):
    """Let GTK size text vertically; only constrain its preferred width.

    Never feed Widget.measure() back into set_size_request(): that result
    already includes the previous request and CSS padding. Doing so creates
    a feedback loop that grows a one-line message on every update. GTK's
    native TextView layout also accounts for markdown tags and width changes.
    """

    def __init__(
        self,
        text="",
        css_classes=(),
        min_height=24,
        markdown=False,
        max_width=None,
        on_resize=None,
    ):
        super().__init__()
        self.set_css_classes(list(css_classes))
        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.set_accepts_tab(False)
        self.set_hexpand(max_width is None)
        self.set_vexpand(False)
        self.set_valign(Gtk.Align.START)

        self._max_width = max_width
        self._min_height = min_height
        self._on_resize_cb = on_resize
        self._refresh_pending = False
        self._last_allocation = None

        self.get_buffer().connect("changed", self._on_buffer_changed)
        self.connect("map", self._on_map)

        link_click = Gtk.GestureClick.new()
        link_click.set_button(1)
        link_click.connect("released", _on_link_clicked, self)
        self.add_controller(link_click)

        if markdown:
            self.set_markdown_text(text or "")
        else:
            self.set_plain_text(text or "")

    def set_plain_text(self, text):
        self.get_buffer().set_text(text or "")

    def set_markdown_text(self, text):
        set_text_view_markdown(self, text or "")

    def _on_buffer_changed(self, _buf):
        self._schedule_refresh()

    def _on_map(self, _widget):
        self.queue_resize()
        self._schedule_refresh()

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL and getattr(self, "_max_width", None):
            buf = self.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            layout = self.create_pango_layout(text)
            width, _height = layout.get_pixel_size()
            natural = min(self._max_width, max(1, width + 8))
            return min(96, natural), natural, -1, -1
        minimum, natural, _min_baseline, _natural_baseline = Gtk.TextView.do_measure(
            self, orientation, for_size
        )
        if orientation == Gtk.Orientation.VERTICAL:
            minimum = max(getattr(self, "_min_height", 24), minimum)
            natural = max(minimum, natural)
        return minimum, natural, -1, -1

    def do_size_allocate(self, width, height, baseline):
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        allocation = (width, height)
        if allocation != self._last_allocation:
            self._last_allocation = allocation
            self._schedule_refresh()

    def _schedule_refresh(self):
        if self._refresh_pending:
            return
        self._refresh_pending = True
        GLib.idle_add(self._refresh_size)

    def _refresh_size(self):
        self._refresh_pending = False
        if self.get_parent() is None or not self.get_mapped():
            return False
        # TextView validates off-screen lines lazily. After reflow, force the
        # final line into its native layout before the parent measures again;
        # otherwise a narrower viewport can retain the old, shorter height.
        self.get_iter_location(self.get_buffer().get_end_iter())
        self.queue_resize()
        if self._on_resize_cb is not None:
            self._on_resize_cb(self)
        return False


# -- markdown rendering --


def _ensure_base_tags(buf):
    table = buf.get_tag_table()
    if table.lookup("md_bold") is None:
        buf.create_tag("md_bold", weight=Pango.Weight.BOLD)
    if table.lookup("md_italic") is None:
        buf.create_tag("md_italic", style=Pango.Style.ITALIC)
    if table.lookup("md_code") is None:
        buf.create_tag(
            "md_code",
            family="monospace",
            background="#f1f3f8",
            foreground="#2b3446",
            scale=0.94,
        )
    if table.lookup("md_code_block") is None:
        buf.create_tag(
            "md_code_block",
            family="monospace",
            background="#f6f7fa",
            foreground="#2b3446",
            scale=0.94,
            left_margin=10,
            right_margin=8,
            pixels_above_lines=1,
            pixels_below_lines=1,
        )
    for level, scale in enumerate(_MD_HEADING_SCALE, start=1):
        name = f"md_heading{level}"
        if table.lookup(name) is None:
            buf.create_tag(
                name,
                weight=Pango.Weight.BOLD,
                scale=scale,
                pixels_above_lines=8 if level == 1 else 6,
                pixels_below_lines=4,
            )
    if table.lookup("md_bullet") is None:
        buf.create_tag("md_bullet", left_margin=4)


def _base_tag(buf, name):
    return buf.get_tag_table().lookup(name)


def _on_link_clicked(gesture, n_press, x, y, view):
    # GTK4 移除了 TextTag 的 "event" 信号：改用点击坐标反查 iter，
    # 命中携带 URL 的 tag 时打开链接
    bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
    found, text_iter = view.get_iter_at_location(bx, by)
    if not found:
        return
    for tag in text_iter.get_tags():
        url = getattr(tag, "md_link_url", None)
        if url:
            open_url_async(url)
            return


def _remove_dynamic_link_tags(buf):
    stale = []

    def collect(tag, acc):
        if getattr(tag, "md_link_url", None) is not None:
            acc.append(tag)

    buf.get_tag_table().foreach(collect, stale)
    for tag in stale:
        buf.get_tag_table().remove(tag)


def _make_link_tag(buf, url):
    tag = buf.create_tag(
        None, underline=Pango.Underline.SINGLE, foreground="#0969da"
    )
    # PyGObject 禁用 qdata(set_data)，直接用 Python 属性携带 URL
    tag.md_link_url = url
    return tag


def _insert_tagged(buf, text, tags=()):
    if not text:
        return
    start_offset = buf.get_end_iter().get_offset()
    buf.insert(buf.get_end_iter(), text)
    start = buf.get_iter_at_offset(start_offset)
    end = buf.get_iter_at_offset(start_offset + len(text))
    for tag in tags:
        buf.apply_tag(tag, start, end)


def _insert_markdown_inline(buf, text, base_tags=()):
    pos = 0
    for match in _MD_INLINE_RE.finditer(text):
        if match.start() > pos:
            _insert_tagged(buf, text[pos : match.start()], base_tags)
        if match.group(1) is not None:
            _insert_tagged(
                buf, match.group(1), (*base_tags, _base_tag(buf, "md_code"))
            )
        elif match.group(2) is not None:
            _insert_tagged(
                buf, match.group(2), (*base_tags, _base_tag(buf, "md_bold"))
            )
        elif match.group(3) is not None:
            link_tag = _make_link_tag(buf, match.group(4))
            _insert_tagged(buf, match.group(3), (*base_tags, link_tag))
        elif match.group(5) is not None:
            _insert_tagged(
                buf, match.group(5), (*base_tags, _base_tag(buf, "md_italic"))
            )
        pos = match.end()
    if pos < len(text):
        _insert_tagged(buf, text[pos:], base_tags)


def set_text_view_markdown(view, text):
    buf = view.get_buffer()
    _ensure_base_tags(buf)
    _remove_dynamic_link_tags(buf)
    buf.set_text("")
    if not text:
        return

    lines = text.splitlines()
    in_code_block = False
    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            _insert_tagged(buf, line, (_base_tag(buf, "md_code_block"),))
        else:
            heading = _MD_HEADING_RE.match(line)
            bullet = _MD_BULLET_RE.match(line)
            numbered = _MD_NUMBERED_RE.match(line)
            if heading:
                level = min(len(heading.group(1)), 4)
                _insert_markdown_inline(
                    buf,
                    heading.group(2).strip(),
                    (_base_tag(buf, f"md_heading{level}"),),
                )
            elif bullet:
                level = min(len(bullet.group(1)) // 2, 4)
                _insert_tagged(
                    buf, "  " * level + "•  ", (_base_tag(buf, "md_bullet"),)
                )
                _insert_markdown_inline(buf, bullet.group(2))
            elif numbered:
                level = min(len(numbered.group(1)) // 2, 4)
                _insert_tagged(
                    buf,
                    "  " * level + f"{numbered.group(2)}. ",
                    (_base_tag(buf, "md_bullet"),),
                )
                _insert_markdown_inline(buf, numbered.group(3))
            else:
                _insert_markdown_inline(buf, line)
        if not is_last:
            _insert_tagged(buf, "\n")


# -- scroll helpers --


def is_at_bottom(adjustment, tolerance=2):
    if adjustment is None:
        return False
    max_value = max(0, adjustment.get_upper() - adjustment.get_page_size())
    return adjustment.get_value() >= max_value - tolerance


def scroll_to_bottom(adjustment):
    if adjustment is None:
        return
    adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))


def restore_after_relayout(adjustment, value, at_bottom=False):
    """等内容重新布局(adjustment "changed")后恢复滚动位置。

    比固定延时定时器可靠：布局慢于延时窗口时旧实现会恢复到过期的
    upper，导致少滚；这里由布局完成事件驱动，另加一次性兜底。
    """
    if adjustment is None:
        return
    state = {"done": False, "changed_id": None}

    def apply():
        if state["done"]:
            return
        state["done"] = True
        if state["changed_id"] is not None:
            adjustment.disconnect(state["changed_id"])
            state["changed_id"] = None
        max_value = max(0, adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(max_value if at_bottom else min(value, max_value))

    def on_changed(_adj):
        apply()

    state["changed_id"] = adjustment.connect("changed", on_changed)
    GLib.timeout_add(50, apply)


def render_preserving_scroll(scrolled, update):
    """重新渲染内容并尽量保持滚动位置；update() 执行实际内容更新。"""
    adjustment = scrolled.get_vadjustment() if scrolled is not None else None
    if adjustment is None:
        update()
        return
    value = adjustment.get_value()
    at_bottom = is_at_bottom(adjustment)
    update()
    restore_after_relayout(adjustment, value, at_bottom)


class StickToBottom:
    """滚动区自动贴底：新内容让可滚范围变大时，若原本贴底则保持贴底。

    监听 vadjustment 的 "changed"(布局完成)而非 idle 猜测，修复发送
    消息后因新气泡高度尚未计入 upper 而滚不到底的问题。
    """

    def __init__(self, scrolled):
        self._adjustment = scrolled.get_vadjustment()
        self._stick = True
        self._adjustment.connect("changed", self._on_changed)
        self._adjustment.connect("value-changed", self._on_value_changed)

    def _on_changed(self, _adj):
        if self._stick:
            scroll_to_bottom(self._adjustment)

    def _on_value_changed(self, _adj):
        self._stick = is_at_bottom(self._adjustment)

    def scroll_bottom(self):
        self._stick = True
        scroll_to_bottom(self._adjustment)


# -- speed stats --


class SpeedStats:
    """流式速度统计，驱动一个 Gtk.Label 显示；label 可随 tab 重建替换。"""

    def __init__(self):
        self._stats = None
        self._label = None

    def set_label(self, label):
        self._label = label
        self.refresh()

    def start(self):
        self._stats = {
            "start": time.monotonic(),
            "chars": 0,
            "completion_tokens": None,
            "cached": False,
            "final": False,
        }
        self.refresh()

    def reset(self):
        self._stats = None
        self.refresh()

    def mark_cached(self):
        stats = self._stats
        if stats is None:
            return
        stats["cached"] = True
        stats["final"] = True
        self.refresh()

    def record_chunk(self, chunk):
        stats = self._stats
        if stats is None or stats["cached"] or not chunk:
            return
        stats["chars"] += len(chunk)
        self.refresh()

    def record_usage(self, usage):
        stats = self._stats
        if stats is None or not isinstance(usage, dict):
            return
        completion_tokens = usage.get("completion_tokens")
        if isinstance(completion_tokens, int) and completion_tokens > 0:
            stats["completion_tokens"] = completion_tokens

    def finish(self):
        stats = self._stats
        if stats is None:
            return
        stats["final"] = True
        self.refresh()

    @staticmethod
    def _fmt_rate(value, unit):
        # Keep the footer chip short: compact integers above 100, one decimal
        # below, so a fast stream never ellipsizes to "速度 81000.0…".
        if value >= 100:
            return f"{value:.0f} {unit}"
        return f"{value:.1f} {unit}"

    def _text(self):
        stats = self._stats
        if stats is None or stats["cached"]:
            return ""
        elapsed = max(0.001, time.monotonic() - stats["start"])
        completion_tokens = stats.get("completion_tokens")
        if stats.get("final") and completion_tokens:
            return self._fmt_rate(completion_tokens / elapsed, "token/s")
        chars = stats.get("chars", 0)
        if chars <= 0:
            return ""
        return self._fmt_rate(chars / elapsed, "字/s")

    def refresh(self):
        if self._label is None:
            return
        text = self._text()
        self._label.set_label(text)
        self._label.set_tooltip_text(f"{SPEED_LABEL}：{text}" if text else None)
        self._label.set_visible(bool(text))


# -- misc helpers --


_css_display = None
_icon_theme = None


def load_styles():
    """Install the application stylesheet once, including for setup windows."""
    global _css_display
    display = Gdk.Display.get_default()
    if display is None or display is _css_display:
        return
    from ..css import CSS

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _css_display = display


def _get_icon_theme():
    """Register the bundled icons with the display's theme so symbolic
    recoloring (CSS ``color``) works for hover/active states too."""
    global _icon_theme
    if _icon_theme is not None:
        return _icon_theme
    display = Gdk.Display.get_default()
    if display is None:
        return None
    theme = Gtk.IconTheme.get_for_display(display)
    icons = Path(__file__).with_name("icons")
    if icons.is_dir():
        # ``pt-`` names are unique to this app, so appending is enough; unlike
        # generic names they cannot be shadowed by the system icon theme.
        theme.add_search_path(str(icons))
    _icon_theme = theme
    return theme


def icon_image(name, size=16):
    """Use bundled symbolic SVGs for a consistent, CSS-recolorable look.

    Bundled files use a ``pt-`` prefix so they can never be shadowed by a
    desktop icon theme (Breeze, for example, ships its own ``edit-symbolic``).
    They live in a GtkIconTheme search path instead of being loaded as plain
    image files, which lets GTK treat them as symbolic masks and recolor them
    from CSS ``color`` for hover/active states.
    """
    theme = _get_icon_theme()
    bundled = f"pt-{name}"
    if (Path(__file__).with_name("icons") / f"{bundled}.svg").is_file():
        name = bundled
    elif theme is not None and not theme.has_icon(name):
        name = "image-missing-symbolic"
    image = Gtk.Image.new_from_icon_name(name)
    image.set_pixel_size(size)
    return image


def icon_button(icon, tooltip, *, label=None, css_classes=("icon-btn",), icon_size=16):
    button = Gtk.Button()
    button.set_css_classes(list(css_classes))
    button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    if label:
        content = Gtk.Box(spacing=5)
        content.set_halign(Gtk.Align.CENTER)
        content.append(icon_image(icon, icon_size))
        content.append(Gtk.Label(label=label))
        button.set_child(content)
    else:
        button.set_child(icon_image(icon, icon_size))
    return button


def text_button(label, *, icon=None, tooltip=None, css_classes=("text-btn",), icon_size=13):
    button = Gtk.Button()
    button.set_css_classes(list(css_classes))
    if tooltip:
        button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    if icon:
        content = Gtk.Box(spacing=4)
        content.set_halign(Gtk.Align.CENTER)
        content.append(icon_image(icon, icon_size))
        content.append(Gtk.Label(label=label))
        button.set_child(content)
    else:
        button.set_label(label)
    return button


def model_dropdown(choices, selected, *, max_chars=20, css_classes=("model-select",)):
    """Compact provider/model selector that never widens the layout.

    The dropdown is intentionally not hexpanding: a full-width dropdown inside
    a toolbar reads as the page's main control instead of a secondary setting.
    """
    dropdown = Gtk.DropDown.new_from_strings(list(choices))
    dropdown.set_css_classes(list(css_classes))
    dropdown.set_tooltip_text(selected)
    dropdown.set_hexpand(False)
    dropdown.set_halign(Gtk.Align.START)
    dropdown.set_valign(Gtk.Align.CENTER)
    display_names = {
        "deepseek-flash": "DeepSeek Flash",
        "deepseek-v4-pro": "DeepSeek Pro",
    }
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, item):
        label = Gtk.Label(xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(max_chars)
        label.set_single_line_mode(True)
        item.set_child(label)

    def bind(_factory, item):
        name = item.get_item().get_string()
        item.get_child().set_label(display_names.get(name, name))

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    dropdown.set_factory(factory)

    # The closed control stays compact; the menu has its own, wider rows so
    # similar model IDs remain distinguishable instead of sharing an ellipsis.
    menu_factory = Gtk.SignalListItemFactory()

    def setup_menu(_factory, item):
        row = Gtk.Box(spacing=16)
        row.set_css_classes(["model-option"])
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        labels.set_hexpand(True)
        for css_class in ("model-option-name", "model-option-id"):
            label = Gtk.Label(xalign=0)
            label.set_css_classes([css_class])
            label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            label.set_max_width_chars(36)
            label.set_single_line_mode(True)
            labels.append(label)
        row.append(labels)
        check = icon_image("check-symbolic", 14)
        check.set_css_classes(["model-option-check"])
        check_slot = Gtk.Box()
        check_slot.set_size_request(14, -1)
        check_slot.set_valign(Gtk.Align.CENTER)
        check_slot.append(check)
        row.append(check_slot)
        item.set_child(row)
        item.bind_property("selected", check, "visible", GObject.BindingFlags.SYNC_CREATE)

    def bind_menu(_factory, item):
        name = item.get_item().get_string()
        row = item.get_child()
        row.set_tooltip_text(name)
        title = row.get_first_child().get_first_child()
        title.set_label(display_names.get(name, name))
        subtitle = title.get_next_sibling()
        subtitle.set_label(name)
        subtitle.set_visible(name in display_names)

    menu_factory.connect("setup", setup_menu)
    menu_factory.connect("bind", bind_menu)
    dropdown.set_list_factory(menu_factory)
    if selected in choices:
        dropdown.set_selected(choices.index(selected))
    dropdown.connect(
        "notify::selected-item",
        lambda widget, _param: widget.set_tooltip_text(
            widget.get_selected_item().get_string()
            if widget.get_selected_item() is not None else ""
        ),
    )
    return dropdown


def empty_state(icon, title, description, action=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_css_classes(["empty-state"])
    box.set_hexpand(True)
    box.set_valign(Gtk.Align.CENTER)
    image = icon_image(icon, 22)
    image.set_halign(Gtk.Align.CENTER)
    image.set_css_classes(["empty-state-icon"])
    box.append(image)
    heading = Gtk.Label(label=title)
    heading.set_css_classes(["empty-state-title"])
    box.append(heading)
    hint = Gtk.Label(label=description)
    hint.set_css_classes(["empty-state-hint"])
    hint.set_wrap(True)
    hint.set_max_width_chars(40)
    hint.set_justify(Gtk.Justification.CENTER)
    box.append(hint)
    if action is not None:
        action.set_halign(Gtk.Align.CENTER)
        action.set_margin_top(4)
        box.append(action)
    return box


def attach_placeholder(scrolled, text_view, placeholder_text):
    """给 TextView 加占位提示(Gtk.TextView 无内置 placeholder)。返回 Overlay。"""
    overlay = Gtk.Overlay()
    overlay.set_hexpand(True)
    overlay.set_child(scrolled)

    placeholder = Gtk.Label(label=placeholder_text)
    placeholder.set_css_classes(["chat-input-placeholder"])
    placeholder.set_halign(Gtk.Align.START)
    placeholder.set_valign(Gtk.Align.START)
    placeholder.set_margin_start(2)
    placeholder.set_margin_top(8)
    placeholder.set_can_target(False)
    overlay.add_overlay(placeholder)

    def sync(_buf):
        placeholder.set_visible(text_view.get_buffer().get_char_count() == 0)

    text_view.get_buffer().connect("changed", sync)
    sync(None)
    return overlay
