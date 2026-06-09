# -*- coding: utf-8 -*-
"""Trigger-Format und Basisklasse der Hotkey-Backends.

Das serialisierte Trigger-Format bleibt zur bestehenden Config kompatibel:
  "key:<name>"     pynput-Spezialtaste (z. B. key:alt_gr)
  "key:vk:<code>"  Virtual-Key-Code (X11-Keysym bzw. Windows-VK)
  "key:char:<c>"   Zeichentaste
  "key:ev:<code>"  Linux-evdev-Keycode (neu, fuer Wayland-Erfassung)
  "mouse:<name>"   Maustaste (left, right, middle, button8, ...)
  "combo:alt+space"
"""

from abc import ABC, abstractmethod
from typing import Callable, List


class HotkeyPermissionError(Exception):
    """Hotkey-Backend kann nicht starten (fehlende Rechte o. ae.)."""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


# Lesbare Namen fuer die Anzeige in den Einstellungen
_KEY_DISPLAY_NAMES = {
    "alt_gr": "AltGr", "alt_l": "Alt Links", "alt_r": "Alt Rechts",
    "ctrl_l": "Strg Links", "ctrl_r": "Strg Rechts",
    "cmd_l": "Super Links", "cmd_r": "Super Rechts",
    "shift_l": "Shift Links", "shift_r": "Shift Rechts",
    "space": "Leertaste", "tab": "Tab", "caps_lock": "Caps Lock",
    "scroll_lock": "Scroll Lock", "print_screen": "Druck", "pause": "Pause",
    "insert": "Einfg", "delete": "Entf", "home": "Pos1", "end": "Ende",
    "page_up": "Bild hoch", "page_down": "Bild runter",
    "num_lock": "Num Lock", "menu": "Menü",
}

_KNOWN_VK = {"65027": "AltGr"}


def display_name(trigger: str) -> str:
    """Menschenlesbarer Name eines serialisierten Triggers."""
    if trigger.startswith("key:vk:"):
        vk = trigger[7:]
        return _KNOWN_VK.get(vk, "Taste (VK {})".format(vk))
    if trigger.startswith("key:ev:"):
        return "Taste (ev {})".format(trigger[7:])
    if trigger.startswith("key:char:"):
        return "Taste '{}'".format(trigger[9:].upper())
    if trigger.startswith("key:"):
        name = trigger[4:]
        return _KEY_DISPLAY_NAMES.get(name, name.replace("_", " ").title())
    if trigger.startswith("mouse:"):
        btn = trigger[6:]
        names = {"left": "Maus Links", "right": "Maus Rechts", "middle": "Maus Mitte"}
        if btn in names:
            return names[btn]
        if btn.startswith("button"):
            try:
                return "Maus Seitentaste {}".format(int(btn[6:]) - 7)
            except ValueError:
                pass
        return "Maus {}".format(btn)
    if trigger.startswith("combo:"):
        combo = trigger[6:]
        if combo == "alt+space":
            return "Alt + Leertaste"
        return combo.upper()
    return trigger


class HotkeyBackend(ABC):
    """Meldet Press/Release der konfigurierten Trigger als Callbacks.

    Die Hold-/Doppel-Tipp-Logik sitzt im TriggerController, nicht hier.
    """

    name = "base"

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]):
        self.on_press = on_press
        self.on_release = on_release

    @abstractmethod
    def set_triggers(self, triggers: List[str]):
        """Uebernimmt die serialisierten Trigger-Strings aus der Config."""

    @abstractmethod
    def start(self):
        ...

    @abstractmethod
    def stop(self):
        ...

    @abstractmethod
    def capture_once(self, callback: Callable[[str], None], timeout: float = 5.0):
        """Erfasst die naechste Taste/Maustaste und liefert sie serialisiert.

        callback(None) bei Abbruch/Timeout.
        """
