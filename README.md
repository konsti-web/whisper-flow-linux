# Whisper Flow

Lokale Sprache-zu-Text-Diktierfunktion für **Linux, macOS und Windows**.
Trigger-Taste gedrückt halten, sprechen — der Text erscheint an der
Cursor-Position. Vollständig lokal, keine Cloud.

Basiert auf [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[whisper.cpp](https://github.com/ggerganov/whisper.cpp) (via pywhispercpp)
oder [openai-whisper](https://github.com/openai/whisper) — je nach Hardware
wird automatisch das schnellste Backend gewählt.

## Features

- **Live-Transkription** — Text erscheint segmentweise *während* des
  Sprechens (VAD-basiertes Chunking, Vorschau ≤ 2 s nach Sprechbeginn);
  der klassische Batch-Modus bleibt als Option erhalten
- **Automatische Hardware-Erkennung** — wählt beim Start Backend, Modell
  und Quantisierung passend zu GPU/CPU/RAM:

  | Hardware | Backend | Gerät |
  |---|---|---|
  | NVIDIA-GPU | faster-whisper | CUDA |
  | Apple Silicon | whisper.cpp | Metal |
  | AMD-GPU mit ROCm | openai-whisper | ROCm |
  | AMD/Intel/sonstige GPU | whisper.cpp | Vulkan |
  | sonst | faster-whisper | CPU (int8) |

  Alles manuell überschreibbar (Einstellungen → Whisper).
- **Lernendes Wörterbuch** — korrigierst du im Verlaufsfenster dasselbe
  Wort 3× gleich (Schwelle konfigurierbar), übernimmt die App die
  Korrektur automatisch. Fachbegriffe/Namen lassen sich manuell pflegen.
  Begriffe fließen als Hotwords/Initial-Prompt in die Erkennung ein,
  gelernte Korrekturen werden zusätzlich deterministisch ersetzt.
- **Klares Status-Feedback** — vier eindeutig unterscheidbare Zustände
  (Farbe *und* Form) in Tray und Overlay: Bereit 🟢 / Aufnahme 🔴 /
  Verarbeitung 🟠 / Fehler ⚠️. Fehler erscheinen immer mit
  Lösungshinweis — kein stilles Scheitern.
- **Zeitersparnis-Statistik** — diktierte Wörter und gesparte Minuten
  gegenüber dem Tippen (Vergleichsbasis konfigurierbar, Default 40 WPM)
- **Hold-to-Record & Doppel-Tipp**, frei belegbare Trigger (Tastatur und
  Maus-Seitentasten), VU-Meter-Overlay mit Live-Textvorschau
- **Vollständig lokal** — nach dem Modell-Download ist keine
  Internetverbindung nötig

## Installation

### Linux (distro-unabhängig, X11 & Wayland)

```bash
git clone https://github.com/konsti-web/whisper-flow-linux.git
cd whisper-flow-linux
./install.sh
```

Das Skript erkennt apt/dnf/pacman, richtet venv, Desktop-Eintrag,
Autostart und den Befehl `whisper-flow` ein.

**Wayland:** Globale Hotkeys laufen über `evdev` — dein Benutzer muss in
der Gruppe `input` sein (`sudo usermod -aG input $USER`, dann neu
anmelden). Fürs automatische Einfügen: `wl-clipboard` + `wtype`
(wlroots) bzw. `ydotool` (GNOME); sonst landet der Text in der
Zwischenablage und eine Benachrichtigung bittet um Strg+V.

**GNOME:** Für das Tray-Icon die Erweiterung *AppIndicator and
KStatusNotifierItem Support* aktivieren.

### macOS

```bash
git clone https://github.com/konsti-web/whisper-flow-linux.git
cd whisper-flow-linux
python3 -m venv venv && source venv/bin/activate
pip install . pywhispercpp        # pywhispercpp = Metal-Backend
whisperflow
```

Beim ersten Start fragt macOS nach zwei Berechtigungen
(Systemeinstellungen → Datenschutz & Sicherheit):
**Mikrofon**, **Eingabeüberwachung** (Hotkeys) und
**Bedienungshilfen** (automatisches Einfügen).

### Windows

```powershell
git clone https://github.com/konsti-web/whisper-flow-linux.git
cd whisper-flow-linux
python -m venv venv; venv\Scripts\activate
pip install .
whisperflow
```

### Pakete

Tagged Releases bauen über GitHub Actions: **AppImage** (Linux),
**.dmg** (macOS), **Inno-Setup-Installer** (Windows). Ein
**Flatpak**-Manifest liegt unter `packaging/flatpak/` (mit dokumentierten
Sandbox-Einschränkungen — AppImage ist unter Linux der empfohlene Weg).

## Bedienung

**Hold-to-Record (Standard):** AltGr gedrückt halten → sprechen →
loslassen. Im Live-Modus erscheint der Text bereits während des
Sprechens, Segment für Segment.

**Doppel-Tipp (optional):** Trigger 2× schnell tippen startet die
freihändige Aufnahme, erneuter Doppel-Tipp stoppt.

**Tray-Menü:** Status, gesparte Zeit, Pause, Modus-Umschaltung
(Live/Batch), Verlauf & Korrekturen, Statistik, Einstellungen.

### Wörterbuch trainieren

1. Tray → **Verlauf & Korrekturen** → Diktat doppelklicken
2. Text korrigieren und speichern
3. Nach 3 gleichen Korrekturen (konfigurierbar) lernt die App den
   Begriff automatisch — sichtbar unter Einstellungen → Wörterbuch,
   dort auch manuell editier- und löschbar

## Konfiguration

Datei: `~/.config/whisper-flow/config.json` (Linux),
`~/Library/Application Support/whisper-flow/` (macOS),
`%LOCALAPPDATA%\whisper-flow\` (Windows) — oder bequem über den
Einstellungsdialog. Alle Auto-Werte (`backend`, `model_size`, `device`,
`compute_type`) lassen sich fest überschreiben.

| Schlüssel | Bedeutung (Auswahl) |
|---|---|
| `mode` | `live` (Streaming) oder `batch` |
| `live_inject` | `segment` (sofort einfügen) oder `end` |
| `vad_silence_ms` | Sprechpause, die ein Segment abschließt |
| `dictionary_learn_threshold` | Korrekturen bis zur Übernahme (Default 3) |
| `typing_wpm` | Vergleichs-Tippgeschwindigkeit für die Statistik |
| `hotkey_backend` | `auto`, `pynput` oder `evdev` |

## Whisper-Modelle

| Modell | Größe | Tempo | Genauigkeit |
|---|---|---|---|
| `tiny` / `base` | 75–150 MB | sehr schnell | mäßig |
| `small` | ~500 MB | schnell | gut |
| `medium` | ~1,5 GB | langsamer | sehr gut |
| `large-v3-turbo` | ~1,6 GB | schnell | exzellent |

Im Auto-Modus wählt die App das größte Modell, das zur Hardware passt.

## Entwicklung & Tests

```bash
pip install numpy platformdirs psutil pytest
python -m pytest tests/ -v
```

Die Tests decken Hardware-Empfehlung, Wörterbuch-Lernlogik,
Statistik-Berechnung, VAD-Segmentierung, Config-Migration und die
Zustandsmaschine ab — ohne Qt- oder Whisper-Abhängigkeit.

## Fehlerbehebung

**„Qt platform plugin xcb" / SIGABRT beim Start (Linux)** — Qt 6.5+
braucht `libxcb-cursor0`: `sudo apt install libxcb-cursor0
libxkbcommon-x11-0` (Fedora: `xcb-util-cursor libxkbcommon-x11`,
Arch: `xcb-util-cursor libxkbcommon-x11`). Neuere Versionen von
Whisper Flow erkennen das vor dem Start und zeigen genau diesen Hinweis;
`install.sh` installiert die Bibliotheken automatisch mit.

**„Lade Modell…" bleibt stehen** — Erster Start lädt das Modell
(~1,6 GB für large-v3-turbo). Tray-Menü zeigt „Bereit", sobald fertig.

**Text wird nicht eingefügt** — Die Benachrichtigung nennt das fehlende
Tool. X11: `xclip`/`xdotool`; Wayland: `wl-clipboard` + `wtype`/`ydotool`;
macOS: Bedienungshilfen-Berechtigung erteilen.

**Hotkeys reagieren nicht (Wayland)** — `pip install evdev` und Benutzer
zur Gruppe `input` hinzufügen (Hinweis erscheint auch in der App).

**CUDA-Fehler (NVIDIA)** — Treiber prüfen (`nvidia-smi`). Die App fällt
automatisch auf CPU zurück und meldet das als Benachrichtigung.

**ROCm (AMD)** — `pip install openai-whisper` und PyTorch mit
ROCm-Index (`pip install torch --index-url
https://download.pytorch.org/whl/rocm6.2`); die Erkennung wählt das
Backend dann automatisch.

**Vulkan (AMD/Intel)** — pywhispercpp mit Vulkan bauen:
`GGML_VULKAN=1 pip install pywhispercpp --no-binary pywhispercpp`

## Lizenz

MIT
