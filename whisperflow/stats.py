# -*- coding: utf-8 -*-
"""Zeitersparnis-Statistik.

Pro Diktat werden Wortzahl und Diktierdauer erfasst. Die Ersparnis ist
  Tippzeit (Woerter / typing_wpm) - Diktierdauer, nie negativ,
und wird pro Diktat berechnet und aufsummiert (das Clamping pro Diktat
verhindert, dass ein einzelnes langsames Diktat die Summe verfaelscht).
typing_wpm ist konfigurierbar (Default 40 WPM).
"""

import json
import threading
import time
from pathlib import Path
from typing import Optional

from whisperflow.config import STATS_FILE, safe_print


def count_words(text: str) -> int:
    return len(text.split())


def saved_seconds(words: int, speech_seconds: float, typing_wpm: float) -> float:
    """Ersparnis eines Diktats gegenueber dem Tippen (>= 0)."""
    if words <= 0 or typing_wpm <= 0:
        return 0.0
    typing_seconds = words / float(typing_wpm) * 60.0
    return max(0.0, typing_seconds - max(0.0, speech_seconds))


class StatsTracker:
    RECENT_LIMIT = 50

    def __init__(self, path: Optional[Path] = None, typing_wpm: float = 40):
        self.path = Path(path) if path else STATS_FILE
        self.typing_wpm = float(typing_wpm)
        self._lock = threading.Lock()
        self.total_words = 0
        self.total_speech_seconds = 0.0
        self.total_processing_seconds = 0.0
        self.total_saved_seconds = 0.0
        self.total_dictations = 0
        self.recent = []  # [{"ts","words","speech_s","saved_s"}]
        self.load()

    # -- Persistenz -----------------------------------------------------------

    def load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.total_words = int(data.get("total_words", 0))
                self.total_speech_seconds = float(data.get("total_speech_seconds", 0.0))
                self.total_processing_seconds = float(data.get("total_processing_seconds", 0.0))
                self.total_saved_seconds = float(data.get("total_saved_seconds", 0.0))
                self.total_dictations = int(data.get("total_dictations", 0))
                self.recent = list(data.get("recent", []))[-self.RECENT_LIMIT:]
        except Exception as e:
            safe_print("[STATISTIK] Konnte nicht geladen werden: {}".format(e))

    def save(self):
        with self._lock:
            data = {
                "total_words": self.total_words,
                "total_speech_seconds": self.total_speech_seconds,
                "total_processing_seconds": self.total_processing_seconds,
                "total_saved_seconds": self.total_saved_seconds,
                "total_dictations": self.total_dictations,
                "recent": self.recent[-self.RECENT_LIMIT:],
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print("[STATISTIK] Konnte nicht gespeichert werden: {}".format(e))

    # -- Erfassung --------------------------------------------------------------

    def record(self, words: int, speech_seconds: float,
               processing_seconds: float = 0.0) -> float:
        """Erfasst ein Diktat; gibt die Ersparnis dieses Diktats zurueck."""
        if words <= 0:
            return 0.0
        saved = saved_seconds(words, speech_seconds, self.typing_wpm)
        with self._lock:
            self.total_words += words
            self.total_speech_seconds += max(0.0, speech_seconds)
            self.total_processing_seconds += max(0.0, processing_seconds)
            self.total_saved_seconds += saved
            self.total_dictations += 1
            self.recent.append({
                "ts": time.time(), "words": words,
                "speech_s": round(speech_seconds, 2), "saved_s": round(saved, 2),
            })
            self.recent = self.recent[-self.RECENT_LIMIT:]
        self.save()
        return saved

    def reset(self):
        with self._lock:
            self.total_words = 0
            self.total_speech_seconds = 0.0
            self.total_processing_seconds = 0.0
            self.total_saved_seconds = 0.0
            self.total_dictations = 0
            self.recent = []
        self.save()

    # -- Auswertung ---------------------------------------------------------------

    def summary(self) -> dict:
        with self._lock:
            speech_min = self.total_speech_seconds / 60.0
            spoken_wpm = (self.total_words / speech_min) if speech_min > 0 else 0.0
            return {
                "total_words": self.total_words,
                "total_dictations": self.total_dictations,
                "total_speech_minutes": speech_min,
                "total_saved_minutes": self.total_saved_seconds / 60.0,
                "avg_spoken_wpm": spoken_wpm,
                "typing_wpm": self.typing_wpm,
            }

    def tray_label(self) -> str:
        s = self.summary()
        return "≈ {:.0f} Min gespart · {} Wörter".format(
            s["total_saved_minutes"], s["total_words"])
