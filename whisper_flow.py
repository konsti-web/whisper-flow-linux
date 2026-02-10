#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper Flow für Linux
Strg gedrückt halten zum Starten/Stoppen der Aufnahme.
Transkribiert mit faster-whisper und fügt Text ein.
Mit System Tray Icon für Kontrolle und Einstellungen.
"""

from __future__ import print_function
import subprocess
import threading
import time
import os
import sys
import json
import signal
import locale
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

from pynput import keyboard
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
    "trigger_key": "altgr",
    "autostart": True,
    "input_device": None  # None = Standard-Gerät
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
        self.recording_rate = SAMPLE_RATE  # Tatsächliche Aufnahme-Rate

        # Hold-to-record detection
        self.key_pressed = False
        self.key_press_time = 0
        self.hold_timer = None
        self.recording_started_by_hold = False
        self.alt_pressed = False

        # Tray Icon
        self.indicator = None
        self.status_item = None

        # Audio-Level Overlay
        self.audio_overlay = None

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

    def load_model(self):
        """Lädt das Whisper Model."""
        model_size = self.config.get("model_size")
        safe_print("Lade Whisper Model '{}' auf GPU...".format(model_size))
        self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
        self.model_loaded = True
        safe_print("Model geladen!")
        self._update_status("Bereit")
        self._show_notification("Whisper Flow", "Bereit - Taste gedrueckt halten zum Diktieren")

    def start_recording(self):
        """Startet die Audioaufnahme."""
        if self.recording or self.paused:
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
            segments, info = self.model.transcribe(
                audio_array,
                language=self.config.get("language"),
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
            import traceback
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
        """Aktualisiert den Status im Tray-Menü."""
        if self.status_item:
            GLib.idle_add(self.status_item.set_label, "Status: {}".format(status))

    def _get_trigger_key(self):
        """Gibt die konfigurierte Trigger-Taste zurück."""
        key_name = self.config.get("trigger_key")
        key_map = {
            "ctrl": (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r),
            "alt": (keyboard.Key.alt_l, keyboard.Key.alt_r),
            "altgr": (keyboard.Key.alt_gr, keyboard.KeyCode.from_vk(65027)),
            "super": (keyboard.Key.cmd_l, keyboard.Key.cmd_r),
        }
        return key_map.get(key_name, key_map["altgr"])

    def _start_recording_after_hold(self):
        """Startet Aufnahme nach Hold-Threshold."""
        if self.key_pressed and not self.recording and not self.paused:
            self.recording_started_by_hold = True
            self.start_recording()

    def on_press(self, key):
        """Handler für Tastendruck."""
        try:
            trigger = self.config.get("trigger_key")
            is_trigger = False

            if trigger == "alt+space":
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self.alt_pressed = True
                elif key == keyboard.Key.space and self.alt_pressed:
                    is_trigger = True
            else:
                trigger_keys = self._get_trigger_key()
                if key in trigger_keys:
                    is_trigger = True

            if is_trigger and not self.key_pressed:
                self.key_pressed = True
                self.key_press_time = time.time()
                self.hold_timer = threading.Timer(
                    self.config.get("hold_threshold"),
                    self._start_recording_after_hold
                )
                self.hold_timer.start()
        except Exception:
            pass

    def on_release(self, key):
        """Handler für Tastenfreigabe."""
        try:
            trigger = self.config.get("trigger_key")
            is_trigger_release = False

            if trigger == "alt+space":
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self.alt_pressed = False
                    is_trigger_release = True
                elif key == keyboard.Key.space:
                    is_trigger_release = True
            else:
                trigger_keys = self._get_trigger_key()
                if key in trigger_keys:
                    is_trigger_release = True

            if is_trigger_release:
                self.key_pressed = False
                if self.hold_timer:
                    self.hold_timer.cancel()
                    self.hold_timer = None
                if self.recording and self.recording_started_by_hold:
                    self.recording_started_by_hold = False
                    self.stop_recording()
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

    def run(self):
        """Startet die Anwendung."""
        self.setup_tray()
        self.audio_overlay = AudioLevelOverlay()

        model_thread = threading.Thread(target=self.load_model)
        model_thread.daemon = True
        model_thread.start()

        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()

        signal.signal(signal.SIGINT, lambda s, f: self.quit())
        signal.signal(signal.SIGTERM, lambda s, f: self.quit())

        trigger = self.config.get('trigger_key')
        trigger_names = {"alt+space": "ALT + LEERTASTE", "altgr": "ALTGR"}
        trigger_display = trigger_names.get(trigger, trigger.upper())
        safe_print("[BEREIT] Whisper Flow gestartet")
        safe_print("         {} gedrueckt halten zum Diktieren".format(trigger_display))
        safe_print("         Tray Icon fuer weitere Optionen\n")

        Gtk.main()


class SettingsDialog(Gtk.Dialog):
    """Einstellungsdialog."""

    def __init__(self, config, app):
        super().__init__(title="Whisper Flow Einstellungen", flags=0)
        self.config = config
        self.app = app

        self.set_default_size(450, 400)
        self.set_border_width(10)

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
            # Kürze lange Namen
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

        # Trigger-Taste
        key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        key_label = Gtk.Label(label="Trigger-Taste:")
        key_label.set_xalign(0)
        key_box.pack_start(key_label, True, True, 0)

        self.key_combo = Gtk.ComboBoxText()
        self.key_combo.append("altgr", "AltGr")
        self.key_combo.append("alt+space", "Alt + Leertaste")
        self.key_combo.append("ctrl", "Strg (Ctrl)")
        self.key_combo.append("alt", "Alt")
        self.key_combo.append("super", "Super (Windows-Taste)")
        self.key_combo.set_active_id(config.get("trigger_key"))
        key_box.pack_start(self.key_combo, False, False, 0)
        control_box.pack_start(key_box, False, False, 0)

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

        control_frame.add(control_box)
        box.pack_start(control_frame, False, False, 0)

        # --- Whisper ---
        whisper_frame = Gtk.Frame(label=" Whisper ")
        whisper_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        whisper_box.set_margin_start(10)
        whisper_box.set_margin_end(10)
        whisper_box.set_margin_top(5)
        whisper_box.set_margin_bottom(10)

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

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            # Einstellungen speichern
            self.config.set("trigger_key", self.key_combo.get_active_id())
            self.config.set("hold_threshold", self.threshold_spin.get_value())
            self.config.set("model_size", self.model_combo.get_active_id())

            # Aufnahmegerät
            device = self.device_combo.get_active_id()
            self.config.set("input_device", None if device == "default" else device)

            lang = self.lang_combo.get_active_id()
            self.config.set("language", None if lang == "auto" else lang)

            # Autostart aktivieren/deaktivieren
            self._set_autostart(self.autostart_check.get_active())

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
