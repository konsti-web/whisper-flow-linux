# -*- coding: utf-8 -*-
"""Texteinfuegen an der Cursor-Position - Plattform-Abstraktion."""

import os
import sys

from whisperflow.inject.base import TextInjector


def get_injector(config) -> TextInjector:
    """Waehlt das passende Injection-Backend fuer die laufende Plattform."""
    if sys.platform == "darwin":
        from whisperflow.inject.macos import MacInjector
        return MacInjector(config)
    if sys.platform.startswith("win"):
        from whisperflow.inject.windows import WindowsInjector
        return WindowsInjector(config)
    # Linux/BSD: Session-Typ entscheidet
    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("XDG_SESSION_TYPE", "") != "x11":
        from whisperflow.inject.linux_wayland import WaylandInjector
        return WaylandInjector(config)
    from whisperflow.inject.linux_x11 import X11Injector
    return X11Injector(config)
