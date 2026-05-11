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

EXTRA_DATA=""
if [ -f "supabase_config.json" ]; then
    EXTRA_DATA='--add-data "supabase_config.json:."'
fi

eval python -m PyInstaller \
    --windowed \
    --name "$APP_NAME" \
    --add-data "shortcuts:shortcuts" \
    --add-data "assets:assets" \
    $EXTRA_DATA \
    --hidden-import "pynput.keyboard._darwin" \
    --hidden-import "pynput.mouse._darwin" \
    --hidden-import "Quartz" \
    --collect-all "pynput" \
    main.py

# Ad-hoc codesign so Finder launches the app without Terminal
codesign --force --deep --sign - "$DIST_DIR/$APP_NAME.app" 2>/dev/null || true

# Zip the .app for distribution (preserves bundle structure + perms)
ZIP_PATH="$DIST_DIR/$APP_NAME.app.zip"
rm -f "$ZIP_PATH"
( cd "$DIST_DIR" && ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$APP_NAME.app.zip" )

echo ""
echo "=== Build complete ==="
echo "App bundle : $DIST_DIR/$APP_NAME.app"
echo "Zip        : $ZIP_PATH"
echo ""
echo "Distribution :"
echo "  1. Envoyer $APP_NAME.app.zip aux utilisateurs"
echo "  2. Dézipper, glisser $APP_NAME.app dans /Applications"
echo "  3. Premier lancement : clic-droit sur l'app → Ouvrir (Gatekeeper)"
echo ""
echo "Accessibility permission (suppression touche Cmd) :"
echo "  Réglages Système → Confidentialité et sécurité → Accessibilité → ajouter $APP_NAME"
