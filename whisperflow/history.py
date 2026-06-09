# -*- coding: utf-8 -*-
"""Verlauf der letzten Diktate.

Dient als Quelle fuer das Woerterbuch-Lernen: Der Nutzer korrigiert ein
Transkript im Verlaufsfenster, der Diff geht an UserDictionary.
"""

import json
import threading
import time
from pathlib import Path
from typing import List, Optional

from whisperflow.config import HISTORY_FILE, safe_print


class HistoryStore:
    LIMIT = 50

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else HISTORY_FILE
        self._lock = threading.Lock()
        self.entries: List[dict] = []  # [{"ts","text","corrected"}] neueste zuletzt
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.entries = list(data.get("entries", []))[-self.LIMIT:]
        except Exception as e:
            safe_print("[VERLAUF] Konnte nicht geladen werden: {}".format(e))

    def save(self):
        with self._lock:
            data = {"entries": self.entries[-self.LIMIT:]}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            safe_print("[VERLAUF] Konnte nicht gespeichert werden: {}".format(e))

    def add(self, text: str) -> dict:
        entry = {"ts": time.time(), "text": text, "corrected": None}
        with self._lock:
            self.entries.append(entry)
            self.entries = self.entries[-self.LIMIT:]
        self.save()
        return entry

    def set_corrected(self, index: int, corrected: str):
        """Speichert die korrigierte Fassung eines Eintrags (Index in entries)."""
        with self._lock:
            if 0 <= index < len(self.entries):
                self.entries[index]["corrected"] = corrected
        self.save()

    def list_entries(self) -> List[dict]:
        with self._lock:
            return list(self.entries)

    def clear(self):
        with self._lock:
            self.entries = []
        self.save()
