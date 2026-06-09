# -*- coding: utf-8 -*-
"""Basisklasse fuer das Texteinfuegen."""

import threading
from abc import ABC, abstractmethod
from typing import Tuple


class TextInjector(ABC):
    """Fuegt Text an der Cursor-Position der fokussierten Anwendung ein.

    inject() gibt (ok, hint) zurueck. Bei ok=False beschreibt hint, was der
    Nutzer tun kann (z. B. fehlendes Tool installieren); der Text liegt dann
    nach Moeglichkeit trotzdem in der Zwischenablage - kein stilles Scheitern.
    """

    name = "base"

    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()  # Einfuegungen serialisieren (Live-Segmente)

    def inject(self, text: str) -> Tuple[bool, str]:
        if not text:
            return True, ""
        with self._lock:
            return self._inject(text)

    @abstractmethod
    def _inject(self, text: str) -> Tuple[bool, str]:
        ...
