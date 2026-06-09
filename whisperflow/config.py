# -*- coding: utf-8 -*-
"""Konfiguration mit plattformgerechten Pfaden und Migration alter Schluessel.

Unter Linux bleibt der bisherige Pfad ~/.config/whisper-flow erhalten,
macOS und Windows bekommen ihre nativen Konfigurationsverzeichnisse.
"""

import json
import os
import sys
from pathlib import Path

try:
    from platformdirs import user_config_dir
except ImportError:
    # Fallback ohne platformdirs (gleiche Pfade fuer die drei Plattformen)
    def user_config_dir(appname, appauthor=None, roaming=False):
        if sys.platform == "darwin":
            return str(Path.home() / "Library" / "Application Support" / appname)
        if sys.platform.startswith("win"):
            base = os.environ.get("LOCALAPPDATA") or str(Path.home())
            return str(Path(base) / appname)
        return str(Path.home() / ".config" / appname)

APP_NAME = "whisper-flow"

CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
CONFIG_FILE = CONFIG_DIR / "config.json"
DICTIONARY_FILE = CONFIG_DIR / "dictionary.json"
STATS_FILE = CONFIG_DIR / "stats.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

DEFAULT_CONFIG = {
    # --- Whisper / Hardware (alle "auto" = automatische Erkennung) ---
    "backend": "auto",        # auto | faster-whisper | whisper-cpp | openai-whisper
    "model_size": "auto",     # auto | tiny | base | small | medium | large-v3 | large-v3-turbo
    "device": "auto",         # auto | cpu | cuda | metal | vulkan
    "compute_type": "auto",   # auto | float16 | int8 | float32 | int8_float16 | int8_float32
    "language": None,         # None = automatisch erkennen

    # --- Steuerung ---
    "hold_threshold": 0.3,
    "trigger_keys": ["key:alt_gr", "key:vk:65027"],
    "double_tap_enabled": False,
    "double_tap_interval": 0.4,
    "hotkey_backend": "auto",  # auto | pynput | evdev

    # --- Audio ---
    "input_device": None,      # None = Standard-Geraet (sonst Geraetename)

    # --- Transkriptionsmodus ---
    "mode": "live",            # live (Streaming) | batch (wie bisher)
    "live_preview_interval": 0.8,   # Sekunden zwischen Vorschau-Updates
    "live_inject": "segment",  # segment = fortlaufend einfuegen | end = am Ende
    "vad_threshold": 0.006,    # RMS-Schwelle (float32, 0..1)
    "vad_silence_ms": 600,     # Stille bis ein Segment finalisiert wird
    "max_segment_s": 15.0,     # Zwangs-Split fuer sehr lange Segmente

    # --- Woerterbuch ---
    "dictionary_enabled": True,
    "dictionary_learning_enabled": True,
    "dictionary_learn_threshold": 3,   # gleiche Korrektur n-mal -> uebernehmen
    "dictionary_use_prompt": True,     # Begriffe als Hotwords/Prompt einspeisen

    # --- Statistik ---
    "stats_enabled": True,
    "typing_wpm": 40,          # Tippgeschwindigkeit fuer Ersparnis-Berechnung

    # --- UI / System ---
    "show_overlay": True,
    "restore_clipboard": True,
    "autostart": True,
}


def safe_print(text):
    """Sicheres Drucken mit Fallback fuer Encoding-Probleme."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


class Config:
    """Laedt/speichert die Konfiguration und migriert alte Schluessel."""

    def __init__(self, config_file=None):
        self.config_file = Path(config_file) if config_file else CONFIG_FILE
        self.config = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        loaded = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.config.update(loaded)
            except Exception as e:
                safe_print("Warnung: Konnte Konfiguration nicht laden: {}".format(e))
        self._migrate(set(loaded.keys()))

    def _migrate(self, loaded_keys):
        """Migriert Schluessel aus aelteren Versionen.

        loaded_keys: Schluessel, die wirklich in der Datei standen (nicht
        nur als Default vorhanden sind).
        """
        changed = False

        # v1: trigger_key (einzeln) -> trigger_keys (Liste)
        if "trigger_key" in self.config:
            old_key = self.config.pop("trigger_key")
            if "trigger_keys" not in loaded_keys:
                migration_map = {
                    "altgr": ["key:alt_gr", "key:vk:65027"],
                    "ctrl": ["key:ctrl_l", "key:ctrl_r"],
                    "alt": ["key:alt_l", "key:alt_r"],
                    "super": ["key:cmd_l", "key:cmd_r"],
                    "alt+space": ["combo:alt+space"],
                }
                self.config["trigger_keys"] = migration_map.get(
                    old_key, list(DEFAULT_CONFIG["trigger_keys"]))
                safe_print("[INFO] Config migriert: trigger_key='{}' -> trigger_keys={}".format(
                    old_key, self.config["trigger_keys"]))
            changed = True

        if changed:
            self.save()

    def save(self):
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print("Fehler: Konnte Konfiguration nicht speichern: {}".format(e))

    def get(self, key):
        value = self.config.get(key, DEFAULT_CONFIG.get(key))
        # None-Werte fuer Schluessel mit nicht-None-Default auf Default zuruecksetzen
        if value is None and DEFAULT_CONFIG.get(key) is not None:
            return DEFAULT_CONFIG[key]
        return value

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def update(self, values):
        """Setzt mehrere Werte und speichert einmal."""
        self.config.update(values)
        self.save()
