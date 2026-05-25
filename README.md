# Pop Translate

A lightweight AI-powered word selection translation tool for Linux Wayland.

Select any text, press a shortcut, and get an instant AI translation and explanation in a clean popup window.

<img src="screenshot.png" width="480" alt="screenshot">

## Features

- **Instant translation** — select text and press shortcut, AI translates automatically
- **Smart language detection** — auto-detects Chinese and English, translates to the other
- **AI explanation** — click "解释" to get a detailed Chinese explanation of unfamiliar concepts
- **Copy translation** — one-click copy to clipboard
- **Native Wayland** — built with GTK4, works natively on modern Linux desktops
- **Auto-resize** — window fits content, max 50% screen height with scroll
- **Zero idle footprint** — exits immediately when closed, no background service

## Requirements

| Dependency | Purpose |
|-----------|---------|
| `python3` | Runtime |
| `python-gobject` | GTK4 Python bindings |
| `gtk4` | GUI toolkit |
| `wl-clipboard` | Get selected text on Wayland |
| `xclip` (optional) | Fallback for X11 selection |

## Quick Start

### 1. Install dependencies

Arch Linux:
```bash
sudo pacman -S python python-gobject gtk4 wl-clipboard xclip
```

Debian/Ubuntu:
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 wl-clipboard xclip
```

Fedora:
```bash
sudo dnf install python3 python3-gobject gtk4 wl-clipboard xclip
```

### 2. Install Pop Translate

```bash
./install.sh
```

### 3. Set your API key

```bash
echo 'export POP_TRANSLATE_API_KEY=sk-your-key-here' >> ~/.bashrc
source ~/.bashrc
```

Supports any OpenAI-compatible API:
- [DeepSeek](https://platform.deepseek.com/) — `https://api.deepseek.com/chat/completions` (recommended, cheap)
- [OpenAI](https://platform.openai.com/) — `https://api.openai.com/v1`
- Any compatible provider

### 4. Set up shortcut

**KDE Plasma:**
- System Settings → Shortcuts → Custom Shortcuts → Add
- Name: `Pop Translate`, Command: `pop-translate`, Shortcut: `Ctrl+Alt+T`

**Other desktops:** Bind `pop-translate` to your preferred shortcut in your WM config.

## Configuration

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POP_TRANSLATE_API_KEY` | *(required)* | Your API key |
| `POP_TRANSLATE_API_URL` | `https://api.deepseek.com/chat/completions` | API endpoint |
| `POP_TRANSLATE_MODEL` | `deepseek-chat` | Model name |

## Usage

1. Select text with your mouse
2. Press `Ctrl+Alt+T` (or your configured shortcut)
3. Popup shows translation
4. Click **解释** to get a detailed AI explanation
5. Click **复制译文** to copy translation to clipboard
6. Press `Esc` or click ✕ to close

## License

MIT
