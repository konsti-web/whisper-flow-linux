#!/bin/bash
# Installation script fuer Whisper Flow (Linux)
# macOS/Windows: siehe README (pip install .)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="whisper-flow"
DESKTOP_FILE="$HOME/.local/share/applications/${APP_NAME}.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/${APP_NAME}.desktop"
BIN_LINK="$HOME/.local/bin/${APP_NAME}"
CONFIG_DIR="$HOME/.config/whisper-flow"

echo "=== Whisper Flow Installation (Linux) ==="
echo ""
echo "Installationsverzeichnis: $SCRIPT_DIR"
echo ""

# Paketmanager erkennen (distro-unabhaengig)
echo "[1/6] Installiere System-Abhaengigkeiten..."
if command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y python3-pip python3-venv python3-dev xclip xdotool || true
    # Wayland-Tools (optional, Paketnamen variieren)
    sudo apt install -y wl-clipboard wtype 2>/dev/null || \
        sudo apt install -y wl-clipboard 2>/dev/null || true
elif command -v dnf &> /dev/null; then
    sudo dnf install -y python3-pip python3-devel xclip xdotool wl-clipboard wtype || true
elif command -v pacman &> /dev/null; then
    sudo pacman -S --needed --noconfirm python-pip xclip xdotool wl-clipboard wtype || true
else
    echo "  Unbekannter Paketmanager - bitte manuell installieren:"
    echo "  python3-venv, python3-dev, xclip, xdotool (X11) bzw. wl-clipboard, wtype (Wayland)"
fi

# Virtual Environment erstellen
echo ""
echo "[2/6] Erstelle virtuelle Umgebung..."
cd "$SCRIPT_DIR"
python3 -m venv venv
source venv/bin/activate

# Python-Pakete installieren
echo ""
echo "[3/6] Installiere Python-Pakete..."
pip install --upgrade pip
pip install -r requirements.txt

# Wayland-Hotkeys (evdev) - optional, braucht python3-dev
if [ -n "$WAYLAND_DISPLAY" ] || [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    echo ""
    echo "  Wayland erkannt - installiere evdev fuer globale Hotkeys..."
    pip install evdev || echo "  WARNUNG: evdev konnte nicht gebaut werden (python3-dev fehlt?)"
    if ! groups | grep -q '\binput\b'; then
        echo ""
        echo "  WICHTIG: Fuer Hotkeys unter Wayland muss dein Benutzer in der Gruppe 'input' sein:"
        echo "    sudo usermod -aG input \$USER"
        echo "  Danach ab- und wieder anmelden."
    fi
fi

# Ausfuehrbar machen
echo ""
echo "[4/6] Mache Skripte ausfuehrbar..."
chmod +x whisper_flow.py run.sh

# Desktop-Datei erstellen
echo ""
echo "[5/6] Erstelle Desktop-Verknuepfung..."
mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Whisper Flow
Comment=Sprache-zu-Text mit Tastendruck
Exec=${SCRIPT_DIR}/run.sh
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Audio;Accessibility;
Keywords=speech;voice;dictation;whisper;transcribe;
StartupNotify=false
EOF

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

mkdir -p "$CONFIG_DIR"

echo ""
echo "=== Installation abgeschlossen! ==="
echo ""
echo "  • Desktop-Verknuepfung: Im Anwendungsmenue unter 'Whisper Flow'"
echo "  • Terminal-Befehl:      whisper-flow"
echo "  • Autostart:            Aktiviert (in den Einstellungen aenderbar)"
echo ""
echo "Starten mit:  whisper-flow"
echo ""
echo "Hinweis GNOME: Fuer das Tray-Icon wird die Erweiterung"
echo "'AppIndicator and KStatusNotifierItem Support' benoetigt."
echo ""
