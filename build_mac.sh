#!/usr/bin/env bash
# Build PTShortcuts.app for macOS
# Run from the project root: bash build_mac.sh
# Requires: pip install pyinstaller pygame-ce pynput pyobjc-framework-Quartz

set -e

DIST_DIR="dist"
APP_NAME="PTShortcuts"

echo "=== PT Shortcuts — macOS build ==="

# Clean previous build
rm -rf build "$DIST_DIR/$APP_NAME.app"

python -m PyInstaller \
    --onefile \
    --windowed \
    --name "$APP_NAME" \
    --add-data "shortcuts:shortcuts" \
    --hidden-import "pynput.keyboard._darwin" \
    --hidden-import "pynput.mouse._darwin" \
    --hidden-import "Quartz" \
    --collect-all "pynput" \
    main.py

echo ""
echo "=== Build complete ==="
echo "Output: $DIST_DIR/$APP_NAME"
echo ""
echo "NOTE: To run without Terminal, codesign the binary:"
echo "  codesign --force --deep --sign - dist/$APP_NAME"
echo ""
echo "Accessibility permission (for Cmd key suppression):"
echo "  System Settings → Privacy & Security → Accessibility → add PTShortcuts"
