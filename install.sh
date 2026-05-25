#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_NAME="pop_translate"
LIB_DIR="$HOME/.local/lib"
BIN_DIR="$HOME/.local/bin"
TARGET_DIR="$LIB_DIR/$PACKAGE_NAME"
WRAPPER="$BIN_DIR/pop-translate"

echo "=== Pop Translate Installer ==="
echo

echo "Checking dependencies..."
MISSING=0

if ! python3 --version &>/dev/null; then
    echo "  [MISSING] python3"
    MISSING=1
else
    echo "  [OK]      python3 ($(python3 --version 2>&1))"
fi

if ! python3 -c "import gi; gi.require_version('Gtk','4.0')" &>/dev/null; then
    echo "  [MISSING] python-gobject + gtk4"
    MISSING=1
else
    echo "  [OK]      python-gobject + gtk4"
fi

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
    echo "  Arch:    sudo pacman -S python python-gobject gtk4 wl-clipboard"
    echo "  Debian:  sudo apt install python3 python3-gi gir1.2-gtk-4.0 wl-clipboard"
    echo "  Fedora:  sudo dnf install python3 python3-gobject gtk4 wl-clipboard"
    exit 1
fi

echo
echo "Installing to $TARGET_DIR..."
mkdir -p "$LIB_DIR"
rm -rf "$TARGET_DIR"
cp -r "$SCRIPT_DIR/$PACKAGE_NAME" "$TARGET_DIR"

echo "Creating wrapper script at $WRAPPER..."
mkdir -p "$BIN_DIR"
cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/bin/sh
exec python3 -m pop_translate "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"

echo
echo "=== Installation complete ==="
echo
echo "Next steps:"
echo "  1. Set your API key (or run pop-translate to configure interactively):"
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
