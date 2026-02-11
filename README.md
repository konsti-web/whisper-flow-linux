# Whisper Flow Linux

Speech-to-text for Linux. Hold a trigger key, speak, and the transcribed text is automatically inserted at the cursor position.

Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with GPU acceleration for fast, local transcription - no cloud, no data leaving your device.

## Features

- **Hold-to-Record** - Hold the trigger key, speak, release to transcribe
- **Double-Tap** - Tap trigger 2x quickly for hands-free dictation (optional)
- **GPU-accelerated** - NVIDIA CUDA for fast transcription
- **VU-Meter Overlay** - Visual audio level display during recording
- **System Tray** - Runs in the background with a tray icon
- **Fully configurable** - Trigger key, language, model, input device
- **Autostart** - Optionally starts with your system
- **Completely local** - No internet connection needed (after model download)

## Requirements

- **Ubuntu/Debian** based Linux (tested on Ubuntu 24.04)
- **NVIDIA GPU** with CUDA support
- **Python 3.10+**
- **X11** (Wayland is not supported due to xdotool/xclip dependency)

## Installation

```bash
git clone https://github.com/konsti-web/whisper-flow-linux.git
cd whisper-flow-linux
./install.sh
```

The install script will:
1. Install system dependencies (xclip, xdotool, portaudio, etc.)
2. Create a Python virtual environment
3. Install faster-whisper and dependencies
4. Create a desktop shortcut and autostart entry
5. Create the `whisper-flow` terminal command

On first launch, the Whisper model will be downloaded (~1.5 GB for `large-v3-turbo`).

## Usage

### Starting

```bash
# Via terminal
whisper-flow

# Or directly
./run.sh

# Or via the application menu
```

### Dictating

**Hold-to-Record (default):**
1. Hold **AltGr**
2. Speak
3. Release - text is transcribed and inserted

**Double-Tap (optional, enable in settings):**
1. Tap **AltGr** twice quickly - recording starts
2. Speak hands-free
3. Tap **AltGr** twice again - recording stops

### Settings

Right-click the tray icon > **Einstellungen** (Settings):

| Setting | Description |
|---|---|
| **Aufnahmegeraet** | Select input microphone |
| **Trigger-Tasten** | Any keyboard or mouse button as trigger |
| **Haltezeit** | Hold duration before recording starts (default: 0.3s) |
| **Doppel-Tipp** | Hands-free dictation via double-tap |
| **Model** | Whisper model size (tiny to large-v3-turbo) |
| **Sprache** | German, English, or Automatic |
| **Autostart** | Start on system boot |

### Changing Trigger Keys

Any key or mouse button can be configured as a trigger in the settings:
- **Keyboard**: AltGr, Ctrl, Alt, Shift, Space, etc.
- **Mouse**: Side buttons (e.g. thumb button)
- Multiple triggers can be active simultaneously

## Whisper Models

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| `tiny` | ~75 MB | Very fast | Low |
| `base` | ~150 MB | Fast | Medium |
| `small` | ~500 MB | Medium | Good |
| `medium` | ~1.5 GB | Slower | Very good |
| `large-v3` | ~3 GB | Slow | Excellent |
| `large-v3-turbo` | ~1.5 GB | Fast | Excellent |

**Recommendation:** `large-v3-turbo` (default) - best balance of speed and accuracy.

## Configuration

Config file: `~/.config/whisper-flow/config.json`

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

## Uninstall

```bash
./uninstall.sh
```

Removes the desktop shortcut, autostart entry, and terminal command. Optionally deletes configuration, virtual environment, and model cache.

## Troubleshooting

**"Model wird noch geladen..." (Model still loading)**
The Whisper model is downloaded on first launch. Wait until the tray menu shows "Bereit" (Ready).

**Text is not inserted**
- Make sure `xclip` and `xdotool` are installed: `sudo apt install xclip xdotool`
- Only works on X11, not Wayland

**No audio / wrong microphone**
- Select the correct input device in settings
- Check that the microphone is enabled in system settings

**CUDA errors**
- NVIDIA drivers installed? Check with `nvidia-smi`
- CUDA is automatically installed via pip (no separate CUDA toolkit needed)

## License

MIT
