# Whisper Flow Linux

Sprache-zu-Text fuer Linux. Trigger-Taste druecken, sprechen, Text wird automatisch an der Cursor-Position eingefuegt.

Nutzt [faster-whisper](https://github.com/SYSTRAN/faster-whisper) mit GPU-Beschleunigung fuer schnelle, lokale Transkription - keine Cloud, keine Daten die dein Geraet verlassen.

## Features

- **Hold-to-Record** - Trigger-Taste gedrückt halten, sprechen, loslassen
- **Doppel-Tipp** - Trigger 2x schnell drücken fuer freihändiges Diktieren (optional)
- **GPU-beschleunigt** - NVIDIA CUDA fuer schnelle Transkription
- **VU-Meter Overlay** - Visuelle Anzeige waehrend der Aufnahme
- **System Tray** - Laeuft im Hintergrund mit Tray-Icon
- **Frei konfigurierbar** - Trigger-Taste, Sprache, Model, Aufnahmegeraet
- **Autostart** - Startet optional mit dem System
- **Komplett lokal** - Keine Internetverbindung noetig (nach Model-Download)

## Voraussetzungen

- **Ubuntu/Debian** basiertes Linux (getestet auf Ubuntu 24.04)
- **NVIDIA GPU** mit CUDA-Support
- **Python 3.10+**
- **X11** (Wayland wird aktuell nicht unterstuetzt wegen xdotool/xclip)

## Installation

```bash
git clone https://github.com/konsti-web/whisper-flow-linux.git
cd whisper-flow-linux
./install.sh
```

Das Install-Script:
1. Installiert System-Abhaengigkeiten (xclip, xdotool, portaudio, etc.)
2. Erstellt eine Python Virtual Environment
3. Installiert faster-whisper und Abhaengigkeiten
4. Erstellt Desktop-Verknuepfung und Autostart
5. Erstellt den Terminal-Befehl `whisper-flow`

Beim ersten Start wird das Whisper-Model heruntergeladen (~1.5 GB fuer `large-v3-turbo`).

## Benutzung

### Starten

```bash
# Ueber Terminal
whisper-flow

# Oder direkt
./run.sh

# Oder ueber das Anwendungsmenue
```

### Diktieren

**Hold-to-Record (Standard):**
1. **AltGr** gedrueckt halten
2. Sprechen
3. Loslassen - Text wird transkribiert und eingefuegt

**Doppel-Tipp (optional, in Einstellungen aktivieren):**
1. **AltGr** 2x schnell druecken - Aufnahme startet
2. Freihaendig sprechen
3. **AltGr** nochmal 2x schnell druecken - Aufnahme stoppt

### Einstellungen

Rechtsklick auf das Tray-Icon > **Einstellungen**:

| Einstellung | Beschreibung |
|---|---|
| **Aufnahmegeraet** | Mikrofon auswaehlen |
| **Trigger-Tasten** | Beliebige Tasten oder Maustasten als Trigger |
| **Haltezeit** | Wie lange halten bevor Aufnahme startet (Standard: 0.3s) |
| **Doppel-Tipp** | Freihaendiges Diktieren per Doppel-Tipp |
| **Model** | Whisper Model-Groesse (tiny bis large-v3-turbo) |
| **Sprache** | Deutsch, Englisch oder Automatisch |
| **Autostart** | Bei Systemstart starten |

### Trigger-Tasten aendern

In den Einstellungen koennen beliebige Tasten als Trigger konfiguriert werden:
- **Tastatur**: AltGr, Strg, Alt, Shift, Leertaste, etc.
- **Maus**: Seitentasten (z.B. Daumentaste)
- Mehrere Trigger gleichzeitig moeglich

## Whisper Models

| Model | Groesse | Geschwindigkeit | Genauigkeit |
|---|---|---|---|
| `tiny` | ~75 MB | Sehr schnell | Niedrig |
| `base` | ~150 MB | Schnell | Mittel |
| `small` | ~500 MB | Mittel | Gut |
| `medium` | ~1.5 GB | Langsamer | Sehr gut |
| `large-v3` | ~3 GB | Langsam | Exzellent |
| `large-v3-turbo` | ~1.5 GB | Schnell | Exzellent |

**Empfehlung:** `large-v3-turbo` (Standard) - beste Balance aus Geschwindigkeit und Genauigkeit.

## Konfiguration

Konfigurationsdatei: `~/.config/whisper-flow/config.json`

```json
{
  "model_size": "large-v3-turbo",
  "language": null,
  "hold_threshold": 0.3,
  "trigger_keys": ["key:alt_gr", "key:vk:65027"],
  "autostart": true,
  "input_device": null,
  "double_tap_enabled": false,
  "double_tap_interval": 0.4
}
```

## Deinstallation

```bash
./uninstall.sh
```

Entfernt Desktop-Verknuepfung, Autostart und Terminal-Befehl. Fragt optional ob Konfiguration, Virtual Environment und Model-Cache geloescht werden sollen.

## Fehlerbehebung

**"Model wird noch geladen..."**
Das Whisper-Model wird beim ersten Start heruntergeladen. Warte bis "Bereit" im Tray-Menue steht.

**Text wird nicht eingefuegt**
- Stelle sicher dass `xclip` und `xdotool` installiert sind: `sudo apt install xclip xdotool`
- Funktioniert nur unter X11, nicht Wayland

**Kein Ton / falsches Mikrofon**
- In den Einstellungen das richtige Aufnahmegeraet auswaehlen
- Pruefen ob das Mikrofon in den System-Einstellungen aktiviert ist

**CUDA Fehler**
- NVIDIA-Treiber installiert? `nvidia-smi` pruefen
- CUDA wird automatisch ueber pip installiert (kein separates CUDA-Toolkit noetig)

## Lizenz

MIT
