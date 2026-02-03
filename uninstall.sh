#!/bin/bash
# Deinstallation script für Whisper Flow Linux

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="whisper-flow"
DESKTOP_FILE="$HOME/.local/share/applications/${APP_NAME}.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/${APP_NAME}.desktop"
BIN_LINK="$HOME/.local/bin/${APP_NAME}"
CONFIG_DIR="$HOME/.config/whisper-flow"

echo "=== Whisper Flow Linux Deinstallation ==="
echo ""

# Laufende Prozesse stoppen
echo "[1/5] Stoppe laufende Prozesse..."
pkill -f "whisper_flow.py" 2>/dev/null && echo "  Whisper Flow Prozess gestoppt" || echo "  Kein laufender Prozess gefunden"

# Desktop-Datei entfernen
echo ""
echo "[2/5] Entferne Desktop-Verknüpfung..."
if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
    echo "  Desktop-Datei entfernt"
else
    echo "  Keine Desktop-Datei gefunden"
fi

# Autostart entfernen
echo ""
echo "[3/5] Entferne Autostart..."
if [ -f "$AUTOSTART_FILE" ]; then
    rm "$AUTOSTART_FILE"
    echo "  Autostart-Datei entfernt"
else
    echo "  Keine Autostart-Datei gefunden"
fi

# Kommandozeilen-Befehl entfernen
echo ""
echo "[4/5] Entferne Terminal-Befehl..."
if [ -f "$BIN_LINK" ]; then
    rm "$BIN_LINK"
    echo "  Befehl 'whisper-flow' entfernt"
else
    echo "  Kein Befehl gefunden"
fi

# Desktop-Datenbank aktualisieren
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

# Fragen ob Konfiguration und venv gelöscht werden sollen
echo ""
echo "[5/5] Optionale Bereinigung..."
echo ""

read -p "Konfiguration löschen? ($CONFIG_DIR) [j/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    rm -rf "$CONFIG_DIR"
    echo "  Konfiguration gelöscht"
else
    echo "  Konfiguration beibehalten"
fi

read -p "Virtuelle Umgebung löschen? ($SCRIPT_DIR/venv) [j/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    rm -rf "$SCRIPT_DIR/venv"
    echo "  Virtuelle Umgebung gelöscht"
else
    echo "  Virtuelle Umgebung beibehalten"
fi

read -p "Whisper-Modell-Cache löschen? (~/.cache/huggingface) [j/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    rm -rf "$HOME/.cache/huggingface/hub/models--Systran--faster-whisper*"
    echo "  Modell-Cache gelöscht"
else
    echo "  Modell-Cache beibehalten"
fi

echo ""
echo "=== Deinstallation abgeschlossen ==="
echo ""
echo "Die Quelldateien wurden nicht gelöscht."
echo "Um alles zu entfernen, lösche das Verzeichnis manuell:"
echo "  rm -rf $SCRIPT_DIR"
echo ""
