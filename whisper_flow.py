#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper Flow fuer Linux
Trigger-Taste gedrueckt halten oder doppelt tippen zum Diktieren.
Transkribiert mit faster-whisper und fuegt Text an der Cursor-Position ein.
Mit System Tray Icon fuer Kontrolle und Einstellungen.
"""

import subprocess
import threading
import time
import os
import sys
import json
import signal
import locale
import traceback
from pathlib import Path

# WICHTIG: C.UTF-8 Locale verwenden - PyAV/FFmpeg hat Probleme mit de_DE
# Muss VOR allen anderen Imports passieren
os.environ['LC_ALL'] = 'C.UTF-8'
os.environ['LANG'] = 'C.UTF-8'
os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'C')
    except locale.Error:
        pass

# Abhängigkeiten prüfen
def check_import(module, package_name):
    try:
        return __import__(module)
    except ImportError:
        print("Fehler: {} nicht installiert. Fuehre aus: pip install {}".format(package_name, package_name))
        sys.exit(1)

check_import('pynput', 'pynput')
check_import('pyaudio', 'pyaudio')
check_import('numpy', 'numpy')
check_import('faster_whisper', 'faster-whisper')

from pynput import keyboard, mouse
import pyaudio
import numpy as np
from faster_whisper import WhisperModel

# GTK und AppIndicator für Tray Icon
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, Gdk, GLib, AppIndicator3
import cairo
import math

# Konfigurationspfade
CONFIG_DIR = Path.home() / ".config" / "whisper-flow"
CONFIG_FILE = CONFIG_DIR / "config.json"
AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "whisper-flow.desktop"
DESKTOP_FILE = Path.home() / ".local" / "share" / "applications" / "whisper-flow.desktop"

# Standard-Konfiguration
DEFAULT_CONFIG = {
    "model_size": "large-v3-turbo",
    "language": None,
    "hold_threshold": 0.3,
    "trigger_keys": ["key:alt_gr", "key:vk:65027"],
    "autostart": True,
    "input_device": None,  # None = Standard-Gerät
    "double_tap_enabled": False,
    "double_tap_interval": 0.4,  # Zeitfenster in Sekunden
    "device": "auto",        # auto | cpu | cuda
    "compute_type": "auto",  # auto | float16 | int8 | float32 | int8_float32
    "backend": "faster-whisper",  # faster-whisper | openai-whisper
}

# Audio-Einstellungen
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024


def safe_print(text):
    """Sicheres Drucken mit Fallback für Encoding-Probleme."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        # Fallback: Ersetze nicht-ASCII Zeichen
        print(text.encode('ascii', 'replace').decode('ascii'), flush=True)


class TriggerSerializer:
    """Serialisiert und deserialisiert Trigger-Tasten."""

    # Mapping von pynput Key-Namen zu lesbaren Display-Namen
    _KEY_DISPLAY_NAMES = {
        "alt_gr": "AltGr",
        "alt_l": "Alt Links",
        "alt_r": "Alt Rechts",
        "ctrl_l": "Strg Links",
        "ctrl_r": "Strg Rechts",
        "cmd_l": "Super Links",
        "cmd_r": "Super Rechts",
        "shift_l": "Shift Links",
        "shift_r": "Shift Rechts",
        "space": "Leertaste",
        "tab": "Tab",
        "caps_lock": "Caps Lock",
        "scroll_lock": "Scroll Lock",
        "print_screen": "Druck",
        "pause": "Pause",
        "insert": "Einfg",
        "delete": "Entf",
        "home": "Pos1",
        "end": "Ende",
        "page_up": "Bild hoch",
        "page_down": "Bild runter",
        "num_lock": "Num Lock",
        "menu": "Menü",
    }

    @staticmethod
    def serialize_keyboard_key(key):
        """Serialisiert einen pynput keyboard Key zu String."""
        if isinstance(key, keyboard.Key):
            return "key:{}".format(key.name)
        elif isinstance(key, keyboard.KeyCode):
            if key.vk is not None:
                return "key:vk:{}".format(key.vk)
            elif key.char is not None:
                return "key:char:{}".format(key.char)
        return None

    @staticmethod
    def serialize_mouse_button(button):
        """Serialisiert einen pynput mouse Button zu String."""
        # pynput mouse.Button hat .name wie 'left', 'right', 'middle', 'button8' etc.
        # Für Xorg-Seitentasten: button8, button9, etc.
        return "mouse:{}".format(button.name)

    @staticmethod
    def deserialize(s):
        """Deserialisiert String zu (typ, pynput_objekte_tuple).

        Returns:
            ("keyboard", (key_obj,)) oder
            ("mouse", (button_obj,)) oder
            ("combo", "alt+space") oder
            None bei Fehler
        """
        try:
            if s.startswith("key:vk:"):
                vk = int(s[7:])
                return ("keyboard", (keyboard.KeyCode.from_vk(vk),))
            elif s.startswith("key:char:"):
                char = s[9:]
                return ("keyboard", (keyboard.KeyCode.from_char(char),))
            elif s.startswith("key:"):
                name = s[4:]
                try:
                    return ("keyboard", (keyboard.Key[name],))
                except KeyError:
                    safe_print("[WARNUNG] Unbekannter Key: {}".format(name))
                    return None
            elif s.startswith("mouse:"):
                btn_name = s[6:]
                try:
                    return ("mouse", (mouse.Button[btn_name],))
                except KeyError:
                    safe_print("[WARNUNG] Unbekannter Mouse-Button: {}".format(btn_name))
                    return None
            elif s.startswith("combo:"):
                return ("combo", s[6:])
        except Exception as e:
            safe_print("[WARNUNG] Trigger-Deserialisierung fehlgeschlagen: {} - {}".format(s, e))
        return None

    @classmethod
    def display_name(cls, s):
        """Gibt einen menschenlesbaren Namen zurück."""
        if s.startswith("key:vk:"):
            vk = s[7:]
            # Bekannte VK-Codes
            known_vk = {"65027": "AltGr"}
            return known_vk.get(vk, "Taste (VK {})".format(vk))
        elif s.startswith("key:char:"):
            char = s[9:]
            return "Taste '{}'".format(char.upper())
        elif s.startswith("key:"):
            name = s[4:]
            return cls._KEY_DISPLAY_NAMES.get(name, name.replace("_", " ").title())
        elif s.startswith("mouse:"):
            btn_name = s[6:]
            if btn_name in ("left", "right", "middle"):
                names = {"left": "Maus Links", "right": "Maus Rechts", "middle": "Maus Mitte"}
                return names[btn_name]
            # button8, button9, etc. -> Seitentaste
            if btn_name.startswith("button"):
                num = btn_name[6:]
                side_num = int(num) - 7  # button8 = Seitentaste 1
                return "Maus Seitentaste {}".format(side_num)
            return "Maus {}".format(btn_name)
        elif s.startswith("combo:"):
            combo = s[6:]
            if combo == "alt+space":
                return "Alt + Leertaste"
            return combo.upper()
        return s


def get_audio_devices():
    """Gibt eine Liste aller verfügbaren Eingabegeräte zurück."""
    devices = []
    pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
                if info.get('maxInputChannels', 0) > 0:
                    name = info.get('name', 'Unknown')
                    # Encoding-sicher machen
                    if isinstance(name, bytes):
                        name = name.decode('utf-8', errors='replace')
                    devices.append({
                        'index': i,
                        'name': name,
                        'channels': info.get('maxInputChannels', 1),
                        'rate': int(info.get('defaultSampleRate', 16000))
                    })
            except Exception:
                pass
    finally:
        pa.terminate()
    return devices


class Config:
    """Verwaltet Konfiguration."""

    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        """Lädt Konfiguration aus Datei."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception as e:
                safe_print("Warnung: Konnte Konfiguration nicht laden: {}".format(e))

        # Migration: trigger_key (alt) -> trigger_keys (neu)
        if "trigger_key" in self.config and "trigger_keys" not in self.config:
            old_key = self.config.pop("trigger_key")
            migration_map = {
                "altgr": ["key:alt_gr", "key:vk:65027"],
                "ctrl": ["key:ctrl_l", "key:ctrl_r"],
                "alt": ["key:alt_l", "key:alt_r"],
                "super": ["key:cmd_l", "key:cmd_r"],
                "alt+space": ["combo:alt+space"],
            }
            self.config["trigger_keys"] = migration_map.get(old_key, ["key:alt_gr", "key:vk:65027"])
            safe_print("[INFO] Config migriert: trigger_key='{}' -> trigger_keys={}".format(
                old_key, self.config["trigger_keys"]))
            self.save()
        elif "trigger_key" in self.config and "trigger_keys" in self.config:
            # Alten Key entfernen falls beide vorhanden
            self.config.pop("trigger_key", None)
            self.save()

    def save(self):
        """Speichert Konfiguration in Datei."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print("Fehler: Konnte Konfiguration nicht speichern: {}".format(e))

    def get(self, key):
        return self.config.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save()


class AudioLevelOverlay:
    """Balken-Anzeige (VU-Meter) als Aufnahme-Overlay mit Audio-Level."""

    NUM_BARS = 7
    BAR_WIDTH = 10
    BAR_GAP = 5
    BAR_MAX_HEIGHT = 60
    BAR_MIN_HEIGHT = 8
    PADDING = 12
    CORNER_RADIUS = 10

    def __init__(self):
        self._level = 0.0
        self._bar_heights = [0.0] * self.NUM_BARS
        self._timer_id = None

        self._width = self.PADDING * 2 + self.NUM_BARS * self.BAR_WIDTH + (self.NUM_BARS - 1) * self.BAR_GAP
        self._height = self.PADDING * 2 + self.BAR_MAX_HEIGHT

        self._window = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._window.set_app_paintable(True)
        self._window.set_decorated(False)
        self._window.set_keep_above(True)
        self._window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self._window.set_accept_focus(False)
        self._window.set_default_size(self._width, self._height)

        screen = self._window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._window.set_visual(visual)

        self._window.connect("draw", self._on_draw)

        # Position: unten mittig auf dem primären Monitor
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        x = geom.x + (geom.width - self._width) // 2
        y = geom.y + geom.height - self._height - 60
        self._window.move(x, y)

    def _make_click_through(self):
        """Setzt eine leere Input-Region, damit Klicks durchgehen."""
        gdk_window = self._window.get_window()
        if gdk_window:
            region = cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
            gdk_window.input_shape_combine_region(region, 0, 0)

    def show_overlay(self):
        """Zeigt das Overlay und startet die Animation."""
        self._bar_heights = [0.0] * self.NUM_BARS
        self._level = 0.0
        self._window.show_all()
        self._make_click_through()
        if self._timer_id is None:
            self._timer_id = GLib.timeout_add(50, self._tick)  # 20fps

    def hide_overlay(self):
        """Versteckt das Overlay und stoppt die Animation."""
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self._window.hide()
        self._bar_heights = [0.0] * self.NUM_BARS
        self._level = 0.0

    def set_level(self, level):
        """Setzt den aktuellen Audio-Level (0.0 - 1.0)."""
        self._level = max(0.0, min(1.0, level))

    def _tick(self):
        """Animation-Tick: Balken-Höhen smoothen und Neuzeichnung."""
        level = self._level
        # Ziel-Höhen pro Balken: mittlere Balken höher (Symmetrie)
        targets = []
        for i in range(self.NUM_BARS):
            # Parabel-Gewichtung: Mitte am höchsten
            dist = abs(i - (self.NUM_BARS - 1) / 2.0) / ((self.NUM_BARS - 1) / 2.0)
            weight = 1.0 - 0.5 * dist * dist
            targets.append(level * weight)
        # Smoothing pro Balken
        for i in range(self.NUM_BARS):
            if targets[i] > self._bar_heights[i]:
                self._bar_heights[i] += (targets[i] - self._bar_heights[i]) * 0.5
            else:
                self._bar_heights[i] += (targets[i] - self._bar_heights[i]) * 0.15
        self._window.queue_draw()
        return True

    def _draw_rounded_rect(self, cr, x, y, w, h, r):
        """Zeichnet ein abgerundetes Rechteck. r wird auf max h/2 begrenzt."""
        r = min(r, h / 2.0, w / 2.0)
        cr.new_path()
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()

    def _on_draw(self, widget, cr):
        """Cairo-Zeichnung: Hintergrund-Panel mit vertikalen Balken."""
        # Transparenter Hintergrund
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        base_y = self._height - self.PADDING

        for i in range(self.NUM_BARS):
            h = self.BAR_MIN_HEIGHT + self._bar_heights[i] * (self.BAR_MAX_HEIGHT - self.BAR_MIN_HEIGHT)
            x = self.PADDING + i * (self.BAR_WIDTH + self.BAR_GAP)
            y = base_y - h

            # Abgerundeter Balken
            self._draw_rounded_rect(cr, x, y, self.BAR_WIDTH, h, self.BAR_WIDTH / 2.0)

            # Farb-Gradient: grün → gelb → rot je nach Höhe
            frac = self._bar_heights[i]
            if frac < 0.5:
                red = frac * 2
                green = 0.8
            else:
                red = 1.0
                green = 0.8 * max(0.0, 1.0 - (frac - 0.5) * 2)
            cr.set_source_rgba(red, green, 0.1, 0.9)
            cr.fill()


class WhisperFlow:
    def __init__(self, config):
        self.config = config
        self.recording = False
        self.paused = False
        self.audio_frames = []
        self.audio_thread = None
        self.pyaudio = pyaudio.PyAudio()
        self.stream = None
        self.model = None
        self.model_loaded = False
        self.listener = None
        self.mouse_listener = None
        self.recording_rate = SAMPLE_RATE  # Tatsächliche Aufnahme-Rate

        # Trigger-Matcher Sets
        self._keyboard_triggers = set()
        self._mouse_triggers = set()
        self._has_alt_space_combo = False

        # Hold-to-record detection
        self.key_pressed = False
        self.key_press_time = 0
        self.hold_timer = None
        self.recording_started_by_hold = False
        self.alt_pressed = False

        # Double-tap detection
        self._last_trigger_release_time = 0
        self._double_tap_recording = False

        # Tray Icon
        self.indicator = None
        self.status_item = None

        # Audio-Level Overlay
        self.audio_overlay = None

        # Backend
        self.backend = self.config.get("backend") or "faster-whisper"

    def get_input_device_index(self):
        """Gibt den Index des konfigurierten Eingabegeräts zurück."""
        device_name = self.config.get("input_device")
        if device_name is None:
            return None  # Standard-Gerät verwenden

        devices = get_audio_devices()
        for dev in devices:
            if dev['name'] == device_name:
                return dev['index']
        return None  # Fallback auf Standard

    @staticmethod
    def detect_device(backend="faster-whisper"):
        """Detect best available device and compute type."""
        if backend == "openai-whisper":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda", "float16"
                return "cpu", "float32"
            except ImportError:
                return "cpu", "float32"
        else:
            import ctranslate2
            try:
                types = ctranslate2.get_supported_compute_types("cuda")
                for ct in ["float16", "int8", "float32"]:
                    if ct in types:
                        return "cuda", ct
                return "cuda", "float32"
            except Exception as e:
                safe_print("[INFO] Kein GPU gefunden ({}), verwende CPU".format(e))
                return "cpu", "int8"

    def load_model(self):
        """Lädt das Whisper Model."""
        model_size = self.config.get("model_size")
        device = self.config.get("device")
        compute_type = self.config.get("compute_type")
        self.backend = self.config.get("backend") or "faster-whisper"

        if device == "auto" or compute_type == "auto":
            det_device, det_compute = self.detect_device(self.backend)
            if device == "auto":
                device = det_device
            if compute_type == "auto":
                compute_type = det_compute

        safe_print("Lade Whisper Model '{}' auf {} ({}) [{}]...".format(model_size, device, compute_type, self.backend))
        self._update_status("Lade Model ({})...".format(device))

        try:
            if self.backend == "openai-whisper":
                import whisper
                self.model = whisper.load_model(model_size, device=device)
            else:
                self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except ImportError as e:
            safe_print("[FEHLER] Backend '{}' nicht installiert: {}".format(self.backend, e))
            self._update_status("Fehler: Backend nicht installiert")
            self._show_notification("Whisper Flow - Fehler",
                                    "Backend '{}' nicht installiert.\n{}".format(self.backend, e))
            return
        except Exception as e:
            if device != "cpu":
                safe_print("[WARNUNG] {} fehlgeschlagen: {}".format(device.upper(), e))
                safe_print("[INFO] Fallback auf CPU...")
                self._show_notification("Whisper Flow", "GPU nicht verfuegbar, verwende CPU")
                try:
                    if self.backend == "openai-whisper":
                        import whisper
                        self.model = whisper.load_model(model_size, device="cpu")
                    else:
                        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
                    device = "cpu"
                except Exception as e2:
                    safe_print("[FEHLER] Model laden fehlgeschlagen: {}".format(e2))
                    self._update_status("Fehler: Model laden fehlgeschlagen")
                    self._show_notification("Whisper Flow - Fehler", str(e2))
                    return
            else:
                safe_print("[FEHLER] Model laden fehlgeschlagen: {}".format(e))
                self._update_status("Fehler: Model laden fehlgeschlagen")
                self._show_notification("Whisper Flow - Fehler", str(e))
                return

        self.model_loaded = True
        device_label = "GPU" if device == "cuda" else "CPU"
        safe_print("Model geladen! (Geraet: {})".format(device_label))
        self._update_status("Bereit ({})".format(device_label))
        self._show_notification("Whisper Flow", "Bereit ({}) - Taste gedrueckt halten zum Diktieren".format(device_label))

    def start_recording(self):
        """Startet die Audioaufnahme."""
        if self.recording or self.paused:
            return

        if not self.model_loaded:
            safe_print("[WARNUNG] Model wird noch geladen...")
            return

        self.recording = True
        self.audio_frames = []

        device_index = self.get_input_device_index()

        try:
            self.recording_rate = SAMPLE_RATE
            self.stream = self.pyaudio.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK_SIZE
            )
        except Exception:
            # Fallback: Native Sample Rate des Geräts verwenden
            try:
                if device_index is not None:
                    dev_info = self.pyaudio.get_device_info_by_index(device_index)
                else:
                    dev_info = self.pyaudio.get_default_input_device_info()
                native_rate = int(dev_info.get('defaultSampleRate', 48000))
                safe_print("[INFO] 16kHz nicht unterstuetzt, verwende {}Hz".format(native_rate))
                self.recording_rate = native_rate
                self.stream = self.pyaudio.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=native_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=CHUNK_SIZE
                )
            except Exception as e:
                safe_print("[FEHLER] Konnte Audio-Stream nicht oeffnen: {}".format(e))
                self.recording = False
                self._update_status("Fehler: Audio")
                return

        self.audio_thread = threading.Thread(target=self._record_audio)
        self.audio_thread.start()

        GLib.idle_add(self.audio_overlay.show_overlay)
        safe_print("[AUFNAHME] Spreche jetzt...")
        self._update_status("Aufnahme...")

    def _record_audio(self):
        """Nimmt Audio auf in separatem Thread."""
        while self.recording:
            try:
                data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                self.audio_frames.append(data)
                # RMS-Level berechnen und an Overlay senden
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(samples ** 2))
                level = min(1.0, rms / 8000.0)
                GLib.idle_add(self.audio_overlay.set_level, level)
            except Exception as e:
                safe_print("Audio-Fehler: {}".format(e))
                break

    def stop_recording(self):
        """Stoppt die Aufnahme und transkribiert."""
        if not self.recording:
            return

        self.recording = False
        GLib.idle_add(self.audio_overlay.hide_overlay)
        self._update_status("Verarbeite...")

        if self.audio_thread:
            self.audio_thread.join(timeout=1.0)

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if not self.audio_frames:
            safe_print("[FEHLER] Keine Audiodaten aufgenommen")
            self._update_status("Bereit")
            return

        safe_print("[VERARBEITE] Transkribiere...")

        try:
            # Audio-Daten als numpy-Array konvertieren
            audio_data = b''.join(self.audio_frames)
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Resample auf 16kHz falls nötig
            if self.recording_rate != SAMPLE_RATE:
                duration = len(audio_array) / self.recording_rate
                target_length = int(duration * SAMPLE_RATE)
                indices = np.linspace(0, len(audio_array) - 1, target_length)
                audio_array = np.interp(indices, np.arange(len(audio_array)), audio_array)

            # Transkribieren - numpy array umgeht PyAV Encoding-Problem
            lang = self.config.get("language")

            if self.backend == "openai-whisper":
                result = self.model.transcribe(
                    audio_array,
                    language=lang,
                    beam_size=1,
                    condition_on_previous_text=False,
                    fp16=(self.config.get("device") != "cpu")
                )
                text = result["text"].strip()
            else:
                segments, info = self.model.transcribe(
                    audio_array,
                    language=lang,
                    beam_size=1,
                    vad_filter=True,
                    condition_on_previous_text=False
                )

                # Explizit als Liste materialisieren
                text_parts = []
                for segment in segments:
                    seg_text = segment.text
                    if seg_text:
                        text_parts.append(seg_text)
                text = " ".join(text_parts).strip()

            if text:
                safe_print("[TEXT] {}".format(text))
                self._copy_and_paste(text)
                display_text = text[:50] + "..." if len(text) > 50 else text
                self._show_notification("Transkribiert", display_text)
            else:
                safe_print("[LEER] Keine Sprache erkannt")

        except Exception as e:
            safe_print("[FEHLER] Transkription fehlgeschlagen: {}".format(e))
            traceback.print_exc()

        finally:
            self._update_status("Bereit")

    def _copy_and_paste(self, text):
        """Kopiert Text in Zwischenablage und fügt ein an Cursor-Position."""
        try:
            # Text als UTF-8 bytes
            text_bytes = text.encode('utf-8')

            process = subprocess.Popen(
                ['xclip', '-selection', 'clipboard'],
                stdin=subprocess.PIPE
            )
            process.communicate(text_bytes)

            process = subprocess.Popen(
                ['xclip', '-selection', 'primary'],
                stdin=subprocess.PIPE
            )
            process.communicate(text_bytes)

            time.sleep(0.15)

            subprocess.run([
                'xdotool', 'key', '--clearmodifiers', 'ctrl+v'
            ], check=True)

        except FileNotFoundError as e:
            safe_print("[FEHLER] Tool nicht gefunden: {}".format(e))
            safe_print("Installiere: sudo apt install xclip xdotool")
        except Exception as e:
            safe_print("[FEHLER] Einfuegen fehlgeschlagen: {}".format(e))

    def _show_notification(self, title, message):
        """Zeigt Desktop-Benachrichtigung."""
        try:
            subprocess.run(
                ['notify-send', '-t', '2000', '-i', 'audio-input-microphone',
                 'Whisper Flow: {}'.format(title), message],
                check=False,
                capture_output=True
            )
        except Exception:
            pass

    def _update_status(self, status):
        """Aktualisiert den Status im Tray-Menü und Icon."""
        if self.status_item:
            GLib.idle_add(self.status_item.set_label, "Status: {}".format(status))
        if self.indicator:
            if "Lade" in status or "Verarbeite" in status:
                icon = "content-loading-symbolic"
            elif "Fehler" in status:
                icon = "dialog-error-symbolic"
            elif "Aufnahme" in status:
                icon = "media-record-symbolic"
            else:
                icon = "audio-input-microphone"
            GLib.idle_add(self.indicator.set_icon, icon)

    def _build_trigger_matchers(self):
        """Baut aus config trigger_keys die Matcher-Sets."""
        self._keyboard_triggers = set()
        self._mouse_triggers = set()
        self._has_alt_space_combo = False

        trigger_keys = self.config.get("trigger_keys")
        if not trigger_keys:
            trigger_keys = DEFAULT_CONFIG["trigger_keys"]

        for s in trigger_keys:
            result = TriggerSerializer.deserialize(s)
            if result is None:
                continue
            typ, value = result
            if typ == "keyboard":
                for obj in value:
                    self._keyboard_triggers.add(obj)
            elif typ == "mouse":
                for obj in value:
                    self._mouse_triggers.add(obj)
            elif typ == "combo" and value == "alt+space":
                self._has_alt_space_combo = True

    def _start_recording_after_hold(self):
        """Startet Aufnahme nach Hold-Threshold."""
        if self.key_pressed and not self.recording and not self.paused:
            self.recording_started_by_hold = True
            self.start_recording()

    def _handle_trigger_press(self):
        """Gemeinsame Press-Logik für Keyboard und Maus-Trigger."""
        if self.key_pressed:
            return
        self.key_pressed = True
        self.key_press_time = time.time()
        self.hold_timer = threading.Timer(
            self.config.get("hold_threshold"),
            self._start_recording_after_hold
        )
        self.hold_timer.start()

    def _handle_trigger_release(self):
        """Gemeinsame Release-Logik für Keyboard und Maus-Trigger."""
        self.key_pressed = False
        if self.hold_timer:
            self.hold_timer.cancel()
            self.hold_timer = None

        now = time.time()
        double_tap_enabled = self.config.get("double_tap_enabled")
        interval = self.config.get("double_tap_interval") or 0.4

        if self.recording and self.recording_started_by_hold:
            # Hold-to-Record: Aufnahme stoppen
            self.recording_started_by_hold = False
            self.stop_recording()
        elif self.recording and self._double_tap_recording:
            # Freihändig-Aufnahme läuft: Doppel-Tipp zum Stoppen?
            if now - self._last_trigger_release_time < interval:
                self._double_tap_recording = False
                self.stop_recording()
            # Sonst: ignorieren, Aufnahme läuft weiter
        elif not self.recording and double_tap_enabled:
            # Keine Aufnahme: Doppel-Tipp zum Starten?
            if now - self._last_trigger_release_time < interval:
                self._double_tap_recording = True
                self.start_recording()

        self._last_trigger_release_time = now

    def on_press(self, key):
        """Handler für Tastendruck."""
        try:
            is_trigger = False

            # Alt+Space Combo
            if self._has_alt_space_combo:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self.alt_pressed = True
                elif key == keyboard.Key.space and self.alt_pressed:
                    is_trigger = True

            # Direkte Keyboard-Trigger
            if key in self._keyboard_triggers:
                is_trigger = True

            if is_trigger:
                self._handle_trigger_press()
        except Exception:
            pass

    def on_release(self, key):
        """Handler für Tastenfreigabe."""
        try:
            is_trigger_release = False

            # Alt+Space Combo
            if self._has_alt_space_combo:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self.alt_pressed = False
                    is_trigger_release = True
                elif key == keyboard.Key.space:
                    is_trigger_release = True

            # Direkte Keyboard-Trigger
            if key in self._keyboard_triggers:
                is_trigger_release = True

            if is_trigger_release:
                self._handle_trigger_release()
        except Exception:
            pass

    def on_mouse_click(self, x, y, button, pressed):
        """Handler für Mausklick (Hold-to-Record und Doppel-Tipp mit Maustasten)."""
        try:
            if button not in self._mouse_triggers:
                return

            if pressed:
                self._handle_trigger_press()
            else:
                self._handle_trigger_release()
        except Exception:
            pass

    def toggle_pause(self, widget=None):
        """Pausiert/Aktiviert die Spracherkennung."""
        self.paused = not self.paused
        status = "Pausiert" if self.paused else "Bereit"
        self._update_status(status)
        self._show_notification("Whisper Flow", "Spracherkennung {}".format(status.lower()))
        safe_print("[INFO] Spracherkennung {}".format(status.lower()))

    def quit(self, widget=None):
        """Beendet die Anwendung."""
        safe_print("\nBeende Whisper Flow...")
        if self.audio_overlay:
            self.audio_overlay.hide_overlay()
        if self.recording:
            self.recording = False
        if self.listener:
            self.listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        try:
            self.pyaudio.terminate()
        except Exception:
            pass
        Gtk.main_quit()

    def show_settings(self, widget=None):
        """Zeigt den Einstellungsdialog."""
        dialog = SettingsDialog(self.config, self)
        dialog.run()
        dialog.destroy()

    def setup_tray(self):
        """Erstellt das System Tray Icon."""
        self.indicator = AppIndicator3.Indicator.new(
            "whisper-flow",
            "audio-input-microphone",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Whisper Flow")

        menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="Status: Lade Model...")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        menu.append(Gtk.SeparatorMenuItem())

        pause_item = Gtk.MenuItem(label="Pausieren / Fortsetzen")
        pause_item.connect("activate", self.toggle_pause)
        menu.append(pause_item)

        settings_item = Gtk.MenuItem(label="Einstellungen...")
        settings_item.connect("activate", self.show_settings)
        menu.append(settings_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Beenden")
        quit_item.connect("activate", self.quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _start_mouse_listener(self):
        """Startet den Mouse-Listener falls Mouse-Trigger konfiguriert sind."""
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None
        if self._mouse_triggers:
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.mouse_listener.start()

    def run(self):
        """Startet die Anwendung."""
        self.setup_tray()
        self.audio_overlay = AudioLevelOverlay()

        self._build_trigger_matchers()

        model_thread = threading.Thread(target=self.load_model)
        model_thread.daemon = True
        model_thread.start()

        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()

        self._start_mouse_listener()

        signal.signal(signal.SIGINT, lambda s, f: self.quit())
        signal.signal(signal.SIGTERM, lambda s, f: self.quit())

        # Alle Trigger-Namen anzeigen
        trigger_keys = self.config.get("trigger_keys") or DEFAULT_CONFIG["trigger_keys"]
        trigger_display = ", ".join(TriggerSerializer.display_name(t) for t in trigger_keys)
        safe_print("[BEREIT] Whisper Flow gestartet")
        safe_print("         Trigger: {}".format(trigger_display))
        safe_print("         Gedrueckt halten zum Diktieren")
        safe_print("         Tray Icon fuer weitere Optionen\n")

        Gtk.main()


class SettingsDialog(Gtk.Dialog):
    """Einstellungsdialog."""

    def __init__(self, config, app):
        super().__init__(title="Whisper Flow Einstellungen", flags=0)
        self.config = config
        self.app = app

        self.set_default_size(450, 500)
        self.set_border_width(10)

        # Lokale Arbeitskopie der Trigger-Liste
        self._trigger_list = list(config.get("trigger_keys") or DEFAULT_CONFIG["trigger_keys"])

        box = self.get_content_area()
        box.set_spacing(10)

        # --- Audio-Einstellungen ---
        audio_frame = Gtk.Frame(label=" Audio ")
        audio_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        audio_box.set_margin_start(10)
        audio_box.set_margin_end(10)
        audio_box.set_margin_top(5)
        audio_box.set_margin_bottom(10)

        # Aufnahmegerät
        device_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        device_label = Gtk.Label(label="Aufnahmegeraet:")
        device_label.set_xalign(0)
        device_box.pack_start(device_label, True, True, 0)

        self.device_combo = Gtk.ComboBoxText()
        self.device_combo.append("default", "Standard (System-Default)")

        devices = get_audio_devices()
        current_device = config.get("input_device")

        for dev in devices:
            name = dev['name']
            if len(name) > 40:
                name = name[:37] + "..."
            self.device_combo.append(dev['name'], name)

        if current_device and current_device != "default":
            self.device_combo.set_active_id(current_device)
        else:
            self.device_combo.set_active_id("default")

        device_box.pack_start(self.device_combo, False, False, 0)
        audio_box.pack_start(device_box, False, False, 0)

        audio_frame.add(audio_box)
        box.pack_start(audio_frame, False, False, 0)

        # --- Steuerung ---
        control_frame = Gtk.Frame(label=" Steuerung ")
        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        control_box.set_margin_start(10)
        control_box.set_margin_end(10)
        control_box.set_margin_top(5)
        control_box.set_margin_bottom(10)

        # Trigger-Tasten Label
        trigger_label = Gtk.Label(label="Trigger-Tasten (gedrueckt halten zum Diktieren):")
        trigger_label.set_xalign(0)
        control_box.pack_start(trigger_label, False, False, 0)

        # Trigger-ListBox in ScrolledWindow
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(80)
        scroll.set_max_content_height(120)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.trigger_listbox = Gtk.ListBox()
        self.trigger_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        scroll.add(self.trigger_listbox)
        control_box.pack_start(scroll, True, True, 0)

        self._refresh_trigger_listbox()

        # Buttons für Trigger-Verwaltung
        trigger_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        capture_btn = Gtk.Button(label="Erfassen...")
        capture_btn.set_tooltip_text("Taste oder Maustaste druecken zum Erfassen")
        capture_btn.connect("clicked", self._on_capture_trigger)
        trigger_btn_box.pack_start(capture_btn, False, False, 0)

        remove_btn = Gtk.Button(label="Entfernen")
        remove_btn.set_tooltip_text("Ausgewaehlten Trigger entfernen")
        remove_btn.connect("clicked", self._on_remove_trigger)
        trigger_btn_box.pack_start(remove_btn, False, False, 0)

        control_box.pack_start(trigger_btn_box, False, False, 0)

        # Hold Threshold
        threshold_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        threshold_label = Gtk.Label(label="Haltezeit (Sekunden):")
        threshold_label.set_xalign(0)
        threshold_box.pack_start(threshold_label, True, True, 0)

        self.threshold_spin = Gtk.SpinButton()
        self.threshold_spin.set_range(0.1, 2.0)
        self.threshold_spin.set_increments(0.1, 0.5)
        self.threshold_spin.set_digits(1)
        self.threshold_spin.set_value(config.get("hold_threshold"))
        threshold_box.pack_start(self.threshold_spin, False, False, 0)
        control_box.pack_start(threshold_box, False, False, 0)

        # Doppel-Tipp Checkbox
        self.double_tap_check = Gtk.CheckButton(label="Doppel-Tipp fuer freihaendiges Diktieren")
        self.double_tap_check.set_tooltip_text(
            "Trigger-Taste 2x schnell druecken = Aufnahme starten/stoppen ohne Halten")
        self.double_tap_check.set_active(config.get("double_tap_enabled") or False)
        control_box.pack_start(self.double_tap_check, False, False, 0)

        control_frame.add(control_box)
        box.pack_start(control_frame, False, False, 0)

        # --- Whisper ---
        whisper_frame = Gtk.Frame(label=" Whisper ")
        whisper_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        whisper_box.set_margin_start(10)
        whisper_box.set_margin_end(10)
        whisper_box.set_margin_top(5)
        whisper_box.set_margin_bottom(10)

        # Backend
        backend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        backend_label = Gtk.Label(label="Backend:")
        backend_label.set_xalign(0)
        backend_box.pack_start(backend_label, True, True, 0)

        self.backend_combo = Gtk.ComboBoxText()
        self.backend_combo.append("faster-whisper", "faster-whisper (Standard)")
        self.backend_combo.append("openai-whisper", "openai-whisper (AMD GPU)")
        self.backend_combo.set_active_id(config.get("backend") or "faster-whisper")
        backend_box.pack_start(self.backend_combo, False, False, 0)
        whisper_box.pack_start(backend_box, False, False, 0)

        # Model Size
        model_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        model_label = Gtk.Label(label="Model:")
        model_label.set_xalign(0)
        model_box.pack_start(model_label, True, True, 0)

        self.model_combo = Gtk.ComboBoxText()
        for model in ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]:
            self.model_combo.append(model, model)
        self.model_combo.set_active_id(config.get("model_size"))
        model_box.pack_start(self.model_combo, False, False, 0)
        whisper_box.pack_start(model_box, False, False, 0)

        # Sprache
        lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lang_label = Gtk.Label(label="Sprache:")
        lang_label.set_xalign(0)
        lang_box.pack_start(lang_label, True, True, 0)

        self.lang_combo = Gtk.ComboBoxText()
        self.lang_combo.append("auto", "Automatisch")
        self.lang_combo.append("de", "Deutsch")
        self.lang_combo.append("en", "Englisch")
        current_lang = config.get("language") or "auto"
        self.lang_combo.set_active_id(current_lang)
        lang_box.pack_start(self.lang_combo, False, False, 0)
        whisper_box.pack_start(lang_box, False, False, 0)

        # Gerät (Device)
        device_hw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        device_hw_label = Gtk.Label(label="Geraet:")
        device_hw_label.set_xalign(0)
        device_hw_box.pack_start(device_hw_label, True, True, 0)

        self.device_hw_combo = Gtk.ComboBoxText()
        self.device_hw_combo.append("auto", "Auto (empfohlen)")
        self.device_hw_combo.append("cpu", "CPU")
        self.device_hw_combo.append("cuda", "CUDA (GPU)")
        self.device_hw_combo.set_active_id(config.get("device") or "auto")
        device_hw_box.pack_start(self.device_hw_combo, False, False, 0)
        whisper_box.pack_start(device_hw_box, False, False, 0)

        # Rechentyp (Compute Type)
        compute_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        compute_label = Gtk.Label(label="Rechentyp:")
        compute_label.set_xalign(0)
        compute_box.pack_start(compute_label, True, True, 0)

        self.compute_combo = Gtk.ComboBoxText()
        self.compute_combo.append("auto", "Auto (empfohlen)")
        self.compute_combo.append("float16", "float16")
        self.compute_combo.append("int8", "int8")
        self.compute_combo.append("float32", "float32")
        self.compute_combo.append("int8_float32", "int8_float32")
        self.compute_combo.set_active_id(config.get("compute_type") or "auto")
        compute_box.pack_start(self.compute_combo, False, False, 0)
        whisper_box.pack_start(compute_box, False, False, 0)

        whisper_frame.add(whisper_box)
        box.pack_start(whisper_frame, False, False, 0)

        # --- System ---
        system_frame = Gtk.Frame(label=" System ")
        system_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        system_box.set_margin_start(10)
        system_box.set_margin_end(10)
        system_box.set_margin_top(5)
        system_box.set_margin_bottom(10)

        # Autostart
        self.autostart_check = Gtk.CheckButton(label="Bei Systemstart automatisch starten")
        self.autostart_check.set_active(AUTOSTART_FILE.exists())
        system_box.pack_start(self.autostart_check, False, False, 0)

        system_frame.add(system_box)
        box.pack_start(system_frame, False, False, 0)

        # Info-Label
        info_label = Gtk.Label()
        info_label.set_markup("<small><i>Hinweis: Model- und Geraete-Aenderungen erfordern Neustart</i></small>")
        info_label.set_xalign(0)
        box.pack_start(info_label, False, False, 5)

        # Buttons
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        save_btn = self.add_button("Speichern", Gtk.ResponseType.OK)
        save_btn.get_style_context().add_class("suggested-action")

        self.connect("response", self.on_response)
        self.show_all()

    def _refresh_trigger_listbox(self):
        """Aktualisiert die ListBox mit den aktuellen Triggern."""
        for child in self.trigger_listbox.get_children():
            self.trigger_listbox.remove(child)
        for trigger_str in self._trigger_list:
            label = Gtk.Label(label=TriggerSerializer.display_name(trigger_str))
            label.set_xalign(0)
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            row = Gtk.ListBoxRow()
            row.add(label)
            row.trigger_str = trigger_str  # Referenz zum Serialisierungsstring
            self.trigger_listbox.add(row)
        self.trigger_listbox.show_all()

    def _on_remove_trigger(self, widget):
        """Entfernt den selektierten Trigger aus der Liste."""
        row = self.trigger_listbox.get_selected_row()
        if row is None:
            return
        trigger_str = row.trigger_str
        if trigger_str in self._trigger_list:
            self._trigger_list.remove(trigger_str)
        self._refresh_trigger_listbox()

    def _on_capture_trigger(self, widget):
        """Öffnet einen modalen Capture-Dialog zum Erfassen einer Taste/Maustaste."""
        dialog = Gtk.Dialog(
            title="Trigger erfassen",
            parent=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        )
        dialog.set_default_size(350, 120)
        dialog.set_border_width(15)

        content = dialog.get_content_area()
        label = Gtk.Label(label="Druecke eine Taste oder Maustaste...\n(Escape = Abbruch, Maus links/rechts/mitte werden ignoriert)")
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        content.pack_start(label, True, True, 10)
        dialog.show_all()

        captured = {}  # {"serialized": str} oder leer bei Abbruch
        temp_kb_listener = None
        temp_mouse_listener = None
        timeout_id = None

        def cleanup_and_close():
            """Stoppt Listener und schließt Dialog."""
            if timeout_id is not None:
                GLib.source_remove(timeout_id)
            if temp_kb_listener is not None:
                try:
                    temp_kb_listener.stop()
                except Exception:
                    pass
            if temp_mouse_listener is not None:
                try:
                    temp_mouse_listener.stop()
                except Exception:
                    pass
            GLib.idle_add(dialog.destroy)

        def on_capture_key_press(key):
            # Escape = Abbruch
            if key == keyboard.Key.esc:
                cleanup_and_close()
                return False
            serialized = TriggerSerializer.serialize_keyboard_key(key)
            if serialized:
                captured["serialized"] = serialized
                cleanup_and_close()
                GLib.idle_add(self._add_captured_trigger, serialized)
            return False  # Stop listener

        def on_capture_mouse_click(x, y, button, pressed):
            if not pressed:
                return  # Nur bei Press reagieren
            # Maus links/rechts/mitte ignorieren (UI-Interaktion)
            if button in (mouse.Button.left, mouse.Button.right, mouse.Button.middle):
                return
            serialized = TriggerSerializer.serialize_mouse_button(button)
            if serialized:
                captured["serialized"] = serialized
                cleanup_and_close()
                GLib.idle_add(self._add_captured_trigger, serialized)
            return False  # Stop listener

        def on_timeout():
            cleanup_and_close()
            return False

        temp_kb_listener = keyboard.Listener(on_press=on_capture_key_press)
        temp_mouse_listener = mouse.Listener(on_click=on_capture_mouse_click)
        temp_kb_listener.start()
        temp_mouse_listener.start()

        # 5s Timeout
        timeout_id = GLib.timeout_add(5000, on_timeout)

    def _add_captured_trigger(self, serialized):
        """Fügt einen erfassten Trigger hinzu falls nicht Duplikat."""
        if serialized not in self._trigger_list:
            self._trigger_list.append(serialized)
            self._refresh_trigger_listbox()

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            # Trigger-Keys speichern
            self.config.config["trigger_keys"] = list(self._trigger_list)
            # Altes trigger_key entfernen falls vorhanden
            self.config.config.pop("trigger_key", None)

            self.config.set("hold_threshold", self.threshold_spin.get_value())
            self.config.set("double_tap_enabled", self.double_tap_check.get_active())
            self.config.set("model_size", self.model_combo.get_active_id())

            # Aufnahmegerät
            device = self.device_combo.get_active_id()
            self.config.set("input_device", None if device == "default" else device)

            lang = self.lang_combo.get_active_id()
            self.config.set("language", None if lang == "auto" else lang)

            self.config.set("backend", self.backend_combo.get_active_id())
            self.config.set("device", self.device_hw_combo.get_active_id())
            self.config.set("compute_type", self.compute_combo.get_active_id())

            # Autostart aktivieren/deaktivieren
            self._set_autostart(self.autostart_check.get_active())

            # Trigger-Matchers neu aufbauen und Mouse-Listener neu starten
            self.app._build_trigger_matchers()
            self.app._start_mouse_listener()

            self.config.save()
            self.app._show_notification("Einstellungen", "Einstellungen gespeichert")

    def _set_autostart(self, enabled):
        """Aktiviert oder deaktiviert Autostart."""
        if enabled:
            AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
            if DESKTOP_FILE.exists():
                import shutil
                shutil.copy(DESKTOP_FILE, AUTOSTART_FILE)
            else:
                content = """[Desktop Entry]
Type=Application
Name=Whisper Flow
Comment=Sprache-zu-Text mit Tastendruck
Exec={}/run.sh
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Audio;
StartupNotify=false
X-GNOME-Autostart-enabled=true
""".format(Path(__file__).parent)
                AUTOSTART_FILE.write_text(content)
        else:
            if AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()


def main():
    # Prüfen ob benötigte Tools installiert sind
    tools = ['xclip', 'xdotool']
    missing = []
    for tool in tools:
        result = subprocess.run(['which', tool], capture_output=True)
        if result.returncode != 0:
            missing.append(tool)

    if missing:
        safe_print("Fehler: Folgende Tools fehlen: {}".format(', '.join(missing)))
        safe_print("Installiere mit: sudo apt install {}".format(' '.join(missing)))
        sys.exit(1)

    config = Config()
    app = WhisperFlow(config)
    app.run()


if __name__ == "__main__":
    main()
