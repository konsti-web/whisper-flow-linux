#!/bin/bash
# Installation script für Whisper Flow Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="whisper-flow"
DESKTOP_FILE="$HOME/.local/share/applications/${APP_NAME}.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/${APP_NAME}.desktop"
BIN_LINK="$HOME/.local/bin/${APP_NAME}"
CONFIG_DIR="$HOME/.config/whisper-flow"

echo "=== Whisper Flow Linux Installation ==="
echo ""
echo "Installationsverzeichnis: $SCRIPT_DIR"
echo ""

# System-Abhängigkeiten
echo "[1/6] Installiere System-Abhängigkeiten..."
sudo apt update
sudo apt install -y \
    xclip \
    xdotool \
    portaudio19-dev \
    python3-pip \
    python3-venv \
    libnotify-bin \
    gir1.2-appindicator3-0.1 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0

# Virtual Environment erstellen
echo ""
echo "[2/6] Erstelle virtuelle Umgebung..."
cd "$SCRIPT_DIR"
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Python-Pakete installieren
echo ""
echo "[3/6] Installiere Python-Pakete..."
pip install --upgrade pip
pip install -r requirements.txt

# Ausführbar machen
echo ""
echo "[4/6] Mache Skripte ausführbar..."
chmod +x whisper_flow.py
chmod +x run.sh

# Desktop-Datei erstellen
echo ""
echo "[5/6] Erstelle Desktop-Verknüpfung..."
mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Whisper Flow
Comment=Sprache-zu-Text mit Tastendruck - Hold Ctrl to dictate
Exec=${SCRIPT_DIR}/run.sh
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Audio;Accessibility;
Keywords=speech;voice;dictation;whisper;transcribe;
StartupNotify=false
EOF

# Desktop-Datenbank aktualisieren
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

# Autostart aktivieren
echo ""
echo "[6/6] Konfiguriere Autostart..."
mkdir -p "$(dirname "$AUTOSTART_FILE")"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
echo "X-GNOME-Autostart-enabled=true" >> "$AUTOSTART_FILE"

# Kommandozeilen-Befehl erstellen
mkdir -p "$HOME/.local/bin"
cat > "$BIN_LINK" << EOF
#!/bin/bash
# Whisper Flow Starter
exec "${SCRIPT_DIR}/run.sh" "\$@"
EOF
chmod +x "$BIN_LINK"

# Konfigurationsverzeichnis erstellen
mkdir -p "$CONFIG_DIR"

echo ""
echo "=== Installation abgeschlossen! ==="
echo ""
echo "Whisper Flow wurde installiert:"
echo ""
echo "  • Desktop-Verknüpfung: Im Anwendungsmenü unter 'Whisper Flow'"
echo "  • Terminal-Befehl:     whisper-flow"
echo "  • Autostart:           Aktiviert (kann in Einstellungen geändert werden)"
echo ""
echo "Starten mit:"
echo "  whisper-flow"
echo ""
echo "Oder über das Anwendungsmenü."
echo ""
echo "Hinweis: Falls 'whisper-flow' nicht gefunden wird, führe aus:"
echo "  source ~/.profile"
echo "  oder starte ein neues Terminal."
echo ""
