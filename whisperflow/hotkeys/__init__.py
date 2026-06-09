# -*- coding: utf-8 -*-
"""Globale Hotkeys - Plattform-Abstraktion.

Backend-Wahl:
  - Linux/Wayland: evdev (liest /dev/input direkt, funktioniert ohne X)
  - Linux/X11, macOS, Windows: pynput
"""

import os
import sys
from typing import Callable, Tuple

from whisperflow.config import safe_print
from whisperflow.hotkeys.base import HotkeyBackend, HotkeyPermissionError


def _is_wayland() -> bool:
    return (sys.platform.startswith("linux")
            and bool(os.environ.get("WAYLAND_DISPLAY"))
            and os.environ.get("XDG_SESSION_TYPE", "") != "x11")


def create_hotkey_backend(config,
                          on_press: Callable[[], None],
                          on_release: Callable[[], None]) -> Tuple[HotkeyBackend, str]:
    """Erzeugt das Hotkey-Backend. Gibt (backend, warnung) zurueck.

    Wirft HotkeyPermissionError, wenn evdev noetig ist, aber die Rechte fehlen.
    """
    choice = config.get("hotkey_backend")
    warning = ""

    if choice == "evdev" or (choice == "auto" and _is_wayland()):
        try:
            from whisperflow.hotkeys.evdev_backend import EvdevHotkeyBackend
            backend = EvdevHotkeyBackend(on_press, on_release)
            backend.check_permissions()
            return backend, warning
        except HotkeyPermissionError:
            raise
        except ImportError:
            if choice == "evdev":
                raise HotkeyPermissionError(
                    "evdev ist nicht installiert.",
                    hint="Installieren mit: pip install evdev (Linux)")
            warning = ("Wayland erkannt, aber python-evdev fehlt - Hotkeys laufen "
                       "ueber X11/XWayland und reagieren evtl. nicht in allen Fenstern. "
                       "Fix: pip install evdev und Nutzer zur Gruppe 'input' hinzufuegen.")
            safe_print("[HOTKEYS] " + warning)

    from whisperflow.hotkeys.pynput_backend import PynputHotkeyBackend
    return PynputHotkeyBackend(on_press, on_release), warning
