#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_NAME="pop_translate"
LIB_DIR="$HOME/.local/lib"
BIN_DIR="$HOME/.local/bin"
TARGET_DIR="$LIB_DIR/$PACKAGE_NAME"
WRAPPER="$BIN_DIR/pop-translate"
URL_WRAPPER="$BIN_DIR/pop-translate-url"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/pop-translate-url.desktop"
CALIBRE_VIEWER_CONFIG="$HOME/.config/calibre/viewer-webengine.json"
POP_TRANSLATE_CALIBRE_URL="pop-translate://explain?q={q}"

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
export PYTHONPATH="$HOME/.local/lib${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m pop_translate "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"

echo "Creating URL handler script at $URL_WRAPPER..."
cat > "$URL_WRAPPER" << 'URL_WRAPPER_EOF'
#!/bin/sh
export PYTHONPATH="$HOME/.local/lib${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m pop_translate.url_handler "$@"
URL_WRAPPER_EOF
chmod +x "$URL_WRAPPER"

echo "Registering pop-translate:// URL handler..."
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Pop Translate URL Handler
Exec=$URL_WRAPPER %u
NoDisplay=true
Terminal=false
MimeType=x-scheme-handler/pop-translate;
DESKTOP_EOF

if command -v xdg-mime &>/dev/null; then
    xdg-mime default pop-translate-url.desktop x-scheme-handler/pop-translate || true
else
    echo "  [WARN] xdg-mime not found; register x-scheme-handler/pop-translate manually if needed"
fi

if [ -f "$CALIBRE_VIEWER_CONFIG" ]; then
    echo "Configuring calibre viewer network search URL..."
    python3 - "$CALIBRE_VIEWER_CONFIG" "$POP_TRANSLATE_CALIBRE_URL" << 'PY_EOF'
import json
import os
import shutil
import sys

path, target_url = sys.argv[1], sys.argv[2]
backup = path + ".bak-pop-translate"

try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as e:
    print(f"  [WARN] Could not read calibre config: {e}")
    raise SystemExit(0)

if data.get("net_search_url") == target_url:
    print("  [OK] calibre net_search_url already configured")
    raise SystemExit(0)

if not os.path.exists(backup):
    shutil.copy2(path, backup)
    print(f"  [OK] backup created: {backup}")

data["net_search_url"] = target_url
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("  [OK] calibre net_search_url -> pop-translate://explain?q={q}")
PY_EOF
else
    echo "  [INFO] calibre viewer config not found; set network search URL manually to:"
    echo "         $POP_TRANSLATE_CALIBRE_URL"
fi

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
echo "  4. calibre integration:"
echo "     Select text in calibre viewer, then click the selection bar network-search button."
echo "     If it still opens a browser, set calibre's internet search URL to:"
echo "     $POP_TRANSLATE_CALIBRE_URL"
echo
echo "  5. Reload shell: source ~/.bashrc"
