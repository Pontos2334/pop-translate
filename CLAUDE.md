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
- `css.py` — All GTK4 CSS as a single bytes literal (macOS-inspired minimal theme).
- `i18n.py` — All UI strings in Chinese, single-file i18n.
- `ui/window.py` — Main popup window. All UI built programmatically (no Glade). Undecorated window with custom drag-to-move title bar, 180s inactivity auto-close. API calls run in daemon threads, results dispatched via `GLib.idle_add()`.
- `ui/setup_dialog.py` — First-run API key configuration wizard.

- Streaming: API calls stream chunks (e.g., chat_stream, translate_stream) and use sse parsing to dynamically update UI.
- Chat Panel: Built dynamically with a custom collapsible expander for reasoning thinking process, inline message copying, settings sync, and context reset callbacks.
