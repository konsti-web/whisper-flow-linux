# -*- coding: utf-8 -*-
"""Texteinfuegen unter Wayland.

Zwischenablage: wl-copy (wl-clipboard).
Einfuegen: wtype (wlroots-Compositors) oder ydotool (universell, braucht
ydotoold). Wenn beides fehlt, bleibt der Text in der Zwischenablage und
der Nutzer bekommt einen klaren Hinweis - kein stilles Scheitern.
"""

import shutil
import subprocess
import time

from whisperflow.inject.base import TextInjector

_INSTALL_HINT = ("Fuer automatisches Einfuegen unter Wayland: "
                 "sudo apt install wl-clipboard wtype  "
                 "(GNOME: ydotool + aktivierter ydotoold-Dienst)")


class WaylandInjector(TextInjector):
    name = "wayland"

    def _set_clipboard(self, text: str) -> bool:
        if not shutil.which("wl-copy"):
            return False
        try:
            proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"), timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    def _paste_keystroke(self) -> bool:
        # 1) wtype: Strg+V (funktioniert auf wlroots: Sway, Hyprland, ...)
        if shutil.which("wtype"):
            try:
                subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"],
                               check=True, timeout=5, capture_output=True)
                return True
            except Exception:
                pass
        # 2) ydotool: Keycodes 29=Strg, 47=V (braucht laufenden ydotoold)
        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
                               check=True, timeout=5, capture_output=True)
                return True
            except Exception:
                pass
        return False

    def _inject(self, text: str):
        if not self._set_clipboard(text):
            return False, ("Zwischenablage konnte nicht gesetzt werden (wl-copy fehlt?). "
                           + _INSTALL_HINT)

        time.sleep(0.15)

        if self._paste_keystroke():
            return True, ""
        return False, ("Text liegt in der Zwischenablage - mit Strg+V einfuegen. "
                       + _INSTALL_HINT)
