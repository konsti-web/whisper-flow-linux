#!/bin/bash
# Baut ein AppImage aus dem PyInstaller-Output.
# Voraussetzungen: pip install pyinstaller; wget; Repo-Root als CWD.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

APPDIR="build/AppDir"
VERSION=$(python3 -c "import whisperflow; print(whisperflow.__version__)")

echo "[1/4] PyInstaller-Build..."
pyinstaller packaging/pyinstaller/whisperflow.spec --noconfirm

echo "[2/4] AppDir zusammenstellen..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -r dist/WhisperFlow/* "$APPDIR/usr/bin/"
cp assets/whisperflow.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/whisperflow.svg"
cp assets/whisperflow.svg "$APPDIR/whisperflow.svg"

cat > "$APPDIR/usr/share/applications/whisperflow.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Whisper Flow
Comment=Lokale Sprache-zu-Text-Diktierfunktion (Whisper)
Exec=whisperflow
Icon=whisperflow
Terminal=false
Categories=Utility;Audio;Accessibility;
EOF
cp "$APPDIR/usr/share/applications/whisperflow.desktop" "$APPDIR/whisperflow.desktop"

cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/whisperflow" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "[3/4] appimagetool besorgen..."
TOOL="build/appimagetool"
if [ ! -x "$TOOL" ]; then
    wget -q -O "$TOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

echo "[4/4] AppImage bauen..."
ARCH=x86_64 "$TOOL" "$APPDIR" "dist/WhisperFlow-${VERSION}-x86_64.AppImage"
echo "Fertig: dist/WhisperFlow-${VERSION}-x86_64.AppImage"
