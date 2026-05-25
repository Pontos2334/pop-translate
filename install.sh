#!/usr/bin/env bash
set -e

SCRIPT_NAME="pop-translate"
INSTALL_DIR="$HOME/.local/bin"
SCRIPT_PATH="$INSTALL_DIR/$SCRIPT_NAME"

echo "=== Pop Translate Installer ==="
echo

check_dep() {
    if ! command -v "$1" &>/dev/null && ! pacman -Q "$1" &>/dev/null 2>&1 && ! dpkg -l "$1" &>/dev/null 2>&1; then
        echo "  [MISSING] $1"
        return 1
    else
        echo "  [OK]      $1"
        return 0
    fi
}

echo "Checking dependencies..."
MISSING=0

# Python
if ! python3 --version &>/dev/null; then
    echo "  [MISSING] python3"
    MISSING=1
else
    echo "  [OK]      python3 ($(python3 --version 2>&1))"
fi

# GTK4
if ! python3 -c "import gi; gi.require_version('Gtk','4.0')" &>/dev/null; then
    echo "  [MISSING] python-gobject + gtk4"
    MISSING=1
else
    echo "  [OK]      python-gobject + gtk4"
fi

# Clipboard
if command -v wl-paste &>/dev/null; then
    echo "  [OK]      wl-clipboard"
elif command -v xclip &>/dev/null; then
    echo "  [OK]      xclip (X11 fallback)"
else
    echo "  [MISSING] wl-clipboard (or xclip)"
    MISSING=1
fi

if [ "$MISSING" -eq 1 ]; then
    echo
    echo "Install missing dependencies first:"
    echo "  Arch:  sudo pacman -S python python-gobject gtk4 wl-clipboard"
    echo "  Debian: sudo apt install python3 python3-gi gir1.2-gtk-4.0 wl-clipboard"
    echo "  Fedora: sudo dnf install python3 python3-gobject gtk4 wl-clipboard"
    exit 1
fi

echo
echo "Installing to $SCRIPT_PATH..."
mkdir -p "$INSTALL_DIR"
cp "$(dirname "$0")/$SCRIPT_NAME" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

echo
echo "=== Installation complete ==="
echo
echo "Next steps:"
echo "  1. Set your API key:"
echo "     echo 'export POP_TRANSLATE_API_KEY=sk-xxxxx' >> ~/.bashrc"
echo
echo "  2. Set your API URL (optional):"
echo "     echo 'export POP_TRANSLATE_API_URL=https://api.deepseek.com/chat/completions' >> ~/.bashrc"
echo
echo "  3. Configure keyboard shortcut:"
echo "     KDE: System Settings → Shortcuts → Add Custom → pop-translate"
echo "     Other: Bind 'pop-translate' in your WM config"
echo
echo "  4. Reload shell: source ~/.bashrc"
