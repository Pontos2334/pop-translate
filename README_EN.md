# Pop Translate

**English** | [中文](./README.md)

A lightweight, beautiful AI-powered word selection translation and explanation tool for Linux (native GTK4, Wayland/X11 support).

Select any text, press a global shortcut, and get instant translation, detailed explanation, or an interactive chat in a premium, hardware-accelerated macOS-style popup window.

![screenshot](screenshot.png)

## ✨ Features

- **🚀 GUI Initial Configuration** — No command-line setup required! If no API key is configured on first start, a beautiful GUI configuration wizard will guide you to set your API Key, API URL, and Model.
- **🎨 Premium macOS Aesthetics** — Upgraded to a minimalist modern light theme featuring capsule pill navigation tab-switching, drop-shadow cards, clean grey borders, custom drop-downs, and a custom optimized font stack (`Inter`, `Cantarell`, `Roboto`, `思源黑体`).
- **🗂️ Powerful Tabbed Workflow**:
  - **Translate (翻译)** — Instant translation with smart bidirectional language detection (English ⇄ Chinese). Support for inline text editing to refine the source text.
  - **Explain (解释)** — Get a detailed explanation of unfamiliar concepts, syntax, or words within a card layout.
  - **Chat (对话)** — Thread-safe, interactive chat view. Ask follow-up questions about the selected text or translation.
- **🧠 Thinking Mode support** — Supports enabling/disabling deep thinking (e.g., DeepSeek R1 / thinking schemas) with a single click or keyboard shortcut.
- **⚡ Keyboard-First Navigation** — Operates entirely mouse-free. Easy-to-remember shortcuts for tab switching, copying, editing, and toggling options.
- **📭 Dynamic Height Auto-Sizing** — Interactive multi-line inputs dynamically grow the window size gracefully when you type, and instantly snap back when the message is sent or cleared.
- **🔒 Security & API Leak Protection** — Automatic redaction and sanitization of API keys, Bearer tokens, or generic `sk-` credentials in error messages or logs.
- **💾 Local SQLite Caching** — Identical selection queries hit a local SQLite cache instantly, avoiding duplicate API calls. Auto-clears entries older than 24 hours to stay lightweight.
- **🛸 Zero Idle Footprint** — Designed as a popup widget. Standard processes exit instantly upon closing, consuming zero background RAM.

---

## ⌨️ Global & Local Keyboard Shortcuts

Pop Translate is designed with keyboard-first users in mind. 

### Local Window Shortcuts (when window is active):
- `S` — Switch to **Translate (翻译)** Tab
- `W` — Switch to **Explain (解释)** Tab
- `C` — Switch to **Chat (对话)** Tab
- `E` — **Edit (编辑)** original text
- `R` — **Regenerate (重生成)** translation / explanation / chat message
- `Y` — **Copy (复制)** translated text (only in Translate tab)
- `F` — **Search (搜索)** selection online (opens in your default browser via Bing, or opens URL directly if selection is a URL)
- `T` — **Toggle Thinking Mode (思考)**
- `X` — **Toggle Context (上下文)** inclusion in Chat mode
- `Esc` — **Close (关闭)** popup window

---

## 📦 Requirements

| Dependency | Purpose |
|-----------|---------|
| `python3` | Runtime |
| `python-gobject` | GTK4 Python bindings |
| `gtk4` | GUI toolkit |
| `wl-clipboard` | Get selected text on Wayland |
| `xclip` (optional) | Fallback for X11 selection |

---

## 🚀 Quick Start

### 1. Install dependencies

**Arch Linux:**
```bash
sudo pacman -S python python-gobject gtk4 wl-clipboard xclip
```

**Debian/Ubuntu:**
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 wl-clipboard xclip
```

**Fedora:**
```bash
sudo dnf install python3 python3-gobject gtk4 wl-clipboard xclip
```

### 2. Install Pop Translate

Clone the repository and run the installer script:
```bash
./install.sh
```

### 3. Initialize & Configure

Simply run `pop-translate` in your terminal or trigger it. 

If it's your first run, a setup wizard will appear:
1. Enter your **API Key** (e.g. your DeepSeek or OpenAI key).
2. Enter your **API URL** (Defaults to `https://api.deepseek.com/chat/completions`).
3. Enter your **Model Name** (e.g. `deepseek-chat`).
4. Click **Save** (保存).

Your configuration will be securely saved to `~/.config/pop-translate/config.json`.

*(Alternatively, you can configure them via environment variables `POP_TRANSLATE_API_KEY`, `POP_TRANSLATE_API_URL`, and `POP_TRANSLATE_MODEL` in your `.bashrc` or `.zshrc`)*

### 4. Configure Global Keyboard Shortcut

**KDE Plasma:**
1. Open **System Settings** → **Shortcuts** → **Custom Shortcuts**.
2. Click **Edit** → **New** → **Global Shortcut** → **Command/URL**.
3. Name it `Pop Translate`.
4. Trigger: Set your desired hotkey (e.g., `Ctrl+Alt+T`).
5. Action: Enter `pop-translate`.
6. Click **Apply**.

**Other Desktops (GNOME, i3, Sway, Hyprland, etc.):**
Bind the executable `pop-translate` to your preferred keyboard shortcut in your desktop environment or window manager settings.

---

## 🛠️ Configuration Options

All settings can be customized through the GUI setup or override via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POP_TRANSLATE_API_KEY` | *(Required)* | OpenAI-compatible API Key |
| `POP_TRANSLATE_API_URL` | `https://api.deepseek.com/chat/completions` | API endpoint URL |
| `POP_TRANSLATE_MODEL` | `deepseek-chat` | Model name |

---

## 🎨 Themes & Styling

The interface features custom styling located in `pop_translate/css.py`. It uses hardware-accelerated GTK4 CSS nodes. You can edit `css.py` to change themes, custom colors, roundness, or font families to match your Linux rice.

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for details.
