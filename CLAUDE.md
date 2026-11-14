# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pop Translate is a lightweight, AI-powered popup translation and explanation tool for Linux. Users select text anywhere on the desktop, press a global hotkey, and a macOS-style GTK4 popup appears with Translate, Explain, Chat, and Vision (screenshot analysis via multimodal LLM) tabs. It uses any OpenAI-compatible API (defaults to DeepSeek) with SQLite caching.

## Commands

```bash
# Install (copies to ~/.local/lib, creates wrapper in ~/.local/bin)
./install.sh

# Run
pop-translate            # read clipboard, show popup
pop-translate --vision   # screenshot region + analyze image with vision model

# Dependencies (Arch Linux)
sudo pacman -S python python-gobject gtk4 wl-clipboard xclip
# Optional: ydotool (Wayland) or xdotool (X11) for auto-copy on hotkey
# Enable ydotool daemon: systemctl --user enable --now ydotool
# Screenshot capture: grim+slurp (Wayland/wlroots) or spectacle/gnome-screenshot/scrot (X11)
```

Automated tests: `pytest tests/`. No build step — pure Python.
Opt-in native GTK layout tests (fixed-size windows, no API/network):
`POP_TRANSLATE_TEST_UI=1 pytest tests/test_ui_layout.py` (needs a display).

## Architecture

**Tech stack:** Python 3, GTK4 (PyGObject), stdlib only (urllib, sqlite3, threading). No pip/pyproject.toml.

**Key files:**

- `__main__.py` — Entry point. Loads config → reads clipboard (or captures a screenshot for `--vision`) → auto-routes to Translate/Explain tab → launches GTK app. Hosts `capture_screenshot()` (grim+slurp / Snipaste / spectacle / gnome-screenshot / scrot).
- `translate.py` — Business logic: `translate()`, `explain()`, `chat()`, prompt construction. Contains `is_code_or_error()` and `should_translate()` heuristics for content auto-routing.
- `vision.py` — Vision tab logic: base64-encodes the captured PNG, builds OpenAI-style multimodal messages (`text` + `image_url` parts), streams analysis via the configured `vision_model`.
- `api.py` — OpenAI-compatible HTTP caller with retry and credential sanitization in error messages.
- `config.py` — Config layering: `~/.config/pop-translate/config.json` + env vars (`POP_TRANSLATE_API_KEY`, `POP_TRANSLATE_API_URL`, `POP_TRANSLATE_MODEL`, `POP_TRANSLATE_VISION_MODEL`). Env vars take precedence.
- `history.py` — SQLite cache with WAL mode, 24h expiry, thread lock. Skipped for non-default models/thinking mode.
- `clipboard.py` — Wayland (`wl-paste`/`wl-copy`) with X11 (`xclip`) fallback. `simulate_copy()` sends Ctrl+Insert via ydotool/xdotool to copy selection before reading.
- `css.py` — All GTK4 CSS as one bytes literal, organized as design tokens plus components. The layout is content-first: a single compact header, a quiet source preview, a hero-size result, and a slim footer for secondary settings. The palette is a muted plum/lavender light theme; the window inherits the desktop's GTK font family, with an explicit 15px base size, medium (500) body text, and semibold (600) controls for readability.
- `i18n.py` — All UI strings in Chinese, single-file i18n.
- `ui/widgets.py` — Shared UI building blocks: `AutoHeightTextView` (GTK-native text height with a bounded preferred width), TextView markdown rendering (bold/italic/code/headings/lists/clickable links), scroll helpers (`render_preserving_scroll`, `restore_after_relayout`), `SpeedStats`, compact text/icon buttons, model selectors that never hexpand, theme-recolored symbolic icons, and empty states. window.py and chat_panel.py must reuse these instead of duplicating logic. Never feed `Widget.measure()` back into `set_size_request()` for text height: CSS padding and the prior request accumulate and create oversized blank bubbles. Validate the final native text line after reflow before requesting layout.
  - Icon rendering: GTK's symbolic renderer only uses SVG fills (strokes render blank/silhouettes), so bundled icons are fill-only. `ui/icons/pt-*-symbolic.svg` are namespaced and `icon_image()` maps base names to the `pt-` file; this prevents desktop icon themes (e.g. Breeze) from shadowing our icons. Icons are CSS-recolorable (`color`) via the icon-theme symbolic path.
- `ui/window.py` — Main popup window. All UI built programmatically (no Glade). Structure: `app-header` (brand mark, four tabs, pin/help/close, also the drag area) → `content_area` → `status-bar` footer (model, thinking, explain mode, regenerate). The footer is hidden for Chat/Vision, the no-text empty state, and edit mode; `_page_toolbar` is kept as an alias of `_status_bar`. The source preview is a non-selectable `Gtk.Label` clamped to three lines with newlines collapsed in the collapsed state; `_sync_source_toggle()` uses Pango's `is_ellipsized()` (not character counts) to decide whether to show 展开. The translation/explanation is the hero: `.result` is 18px, explanations are 17px, and the source is 15px. Undecorated window with custom drag area and 180s inactivity auto-close. API calls run in daemon threads, results dispatched via `GLib.idle_add()`; worker threads wrap streaming loops in try/except and report failures via an inline error banner with a retry action / `ChatPanel.fail_stream`. Pages size to their contents within the current monitor's height budget; the footer and composers sit outside scrolling content. Keyboard shortcut help lives in a popover behind the keyboard button instead of a permanent hint bar.
- `ui/setup_dialog.py` — First-run API key configuration wizard. `on_saved` fires exactly once via the close-request path (works for save, cancel, and window-manager close).

- Streaming: API calls stream chunks (e.g., chat_stream, translate_stream) and use sse parsing to dynamically update UI.
- Chat Panel: A single composer card contains the input plus model/thinking/context/clear/send controls; assistant messages are borderless and user messages use a soft accent bubble. Built dynamically with a custom collapsible expander for reasoning, inline message copying, settings sync, and context reset callbacks. `set_content_height_limit()` budgets the transcript after the attachment strip and composer.
