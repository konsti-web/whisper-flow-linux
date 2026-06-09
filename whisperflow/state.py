# -*- coding: utf-8 -*-
"""Zentrale Zustandsmaschine fuer das Status-Feedback.

Alle UI-Elemente (Tray-Icon, Overlay, Benachrichtigungen) haengen sich als
Listener an dieselbe Zustandsmaschine und bleiben dadurch konsistent.
Die erlaubten Uebergaenge schuetzen zusaetzlich vor Races, z. B. einem
Aufnahme-Start, waehrend noch transkribiert wird.
"""

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List


class AppState(Enum):
    LOADING = "loading"        # Modell wird geladen
    READY = "ready"            # Bereit fuer Diktat
    RECORDING = "recording"    # Aufnahme laeuft
    PROCESSING = "processing"  # Transkription laeuft
    ERROR = "error"            # Fehler, Eingreifen noetig
    PAUSED = "paused"          # Erkennung pausiert


# Erlaubte Zustandsuebergaenge. ERROR ist aus jedem Zustand erreichbar,
# aus ERROR heraus darf direkt wieder aufgenommen werden (Retry).
_ALLOWED = {
    AppState.LOADING: {AppState.READY, AppState.ERROR, AppState.PAUSED, AppState.LOADING},
    AppState.READY: {AppState.RECORDING, AppState.PAUSED, AppState.ERROR,
                     AppState.LOADING, AppState.READY},
    AppState.RECORDING: {AppState.PROCESSING, AppState.READY, AppState.ERROR},
    AppState.PROCESSING: {AppState.READY, AppState.ERROR},
    AppState.ERROR: {AppState.READY, AppState.LOADING, AppState.PAUSED,
                     AppState.RECORDING, AppState.ERROR},
    AppState.PAUSED: {AppState.READY, AppState.LOADING, AppState.ERROR},
}

# Anzeigenamen fuer UI und Logs
STATE_LABELS = {
    AppState.LOADING: "Lade Modell...",
    AppState.READY: "Bereit",
    AppState.RECORDING: "Aufnahme",
    AppState.PROCESSING: "Verarbeite...",
    AppState.ERROR: "Fehler",
    AppState.PAUSED: "Pausiert",
}


@dataclass(frozen=True)
class StateInfo:
    state: AppState
    message: str = ""   # Kurzbeschreibung (Tray-Status)
    hint: str = ""      # Loesungshinweis bei Fehlern

    @property
    def label(self) -> str:
        return self.message or STATE_LABELS[self.state]


class StateMachine:
    """Thread-sichere Zustandsmaschine mit Listener-Benachrichtigung."""

    def __init__(self):
        self._lock = threading.RLock()
        self._info = StateInfo(AppState.LOADING)
        self._listeners: List[Callable[[StateInfo], None]] = []

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._info.state

    @property
    def info(self) -> StateInfo:
        with self._lock:
            return self._info

    def add_listener(self, fn: Callable[[StateInfo], None]):
        with self._lock:
            self._listeners.append(fn)

    def is_in(self, *states: AppState) -> bool:
        with self._lock:
            return self._info.state in states

    def transition(self, state: AppState, message: str = "", hint: str = "") -> bool:
        """Wechselt den Zustand, falls der Uebergang erlaubt ist.

        Returns:
            True bei erfolgtem Wechsel, False wenn der Uebergang verweigert wurde.
        """
        with self._lock:
            if state not in _ALLOWED[self._info.state]:
                return False
            self._info = StateInfo(state, message, hint)
            listeners = list(self._listeners)
            info = self._info
        # Listener ausserhalb des Locks aufrufen (Deadlock-Schutz)
        for fn in listeners:
            try:
                fn(info)
            except Exception:
                pass
        return True

    def error(self, message: str, hint: str = "") -> bool:
        """Wechselt in den Fehlerzustand (aus jedem Zustand erlaubt)."""
        return self.transition(AppState.ERROR, message, hint)
