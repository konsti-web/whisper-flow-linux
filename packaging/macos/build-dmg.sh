#!/bin/bash
# Baut WhisperFlow.app und ein .dmg (auf macOS ausfuehren).
# Voraussetzungen: pip install pyinstaller; optional: pip install .[whispercpp]

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

VERSION=$(python3 -c "import whisperflow; print(whisperflow.__version__)")

echo "[1/2] PyInstaller-Build (.app)..."
pyinstaller packaging/pyinstaller/whisperflow.spec --noconfirm

echo "[2/2] DMG erstellen..."
DMG="dist/WhisperFlow-${VERSION}.dmg"
rm -f "$DMG"
mkdir -p build/dmg
rm -rf build/dmg/*
cp -R "dist/WhisperFlow.app" build/dmg/
ln -sf /Applications build/dmg/Applications
hdiutil create -volname "Whisper Flow" -srcfolder build/dmg -ov -format UDZO "$DMG"
echo "Fertig: $DMG"
echo ""
echo "Hinweis: Fuer Verteilung ausserhalb des eigenen Rechners sollte die App"
echo "signiert und notarisiert werden (codesign / notarytool)."
