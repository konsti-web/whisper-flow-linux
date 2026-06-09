# -*- coding: utf-8 -*-
"""Texteinfuegen unter X11: xclip (Zwischenablage) + xdotool (Strg+V)."""

import shutil
import subprocess
import threading
import time

from whisperflow.inject.base import TextInjector

_INSTALL_HINT = "Installieren mit: sudo apt install xclip xdotool (bzw. dnf/pacman)"


class X11Injector(TextInjector):
    name = "x11"

    def _read_clipboard(self):
        try:
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                    capture_output=True, timeout=2)
            if result.returncode == 0:
                return result.stdout.decode("utf-8")
        except Exception:
            pass
        return None

    def _set_clipboard(self, text: str) -> bool:
        data = text.encode("utf-8")
        try:
            for selection in ("clipboard", "primary"):
                proc = subprocess.Popen(["xclip", "-selection", selection],
                                        stdin=subprocess.PIPE)
                proc.communicate(data, timeout=5)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def _inject(self, text: str):
        if not shutil.which("xclip"):
            return False, "xclip fehlt - Text konnte nicht eingefuegt werden. " + _INSTALL_HINT

        previous = self._read_clipboard() if self.config.get("restore_clipboard") else None

        if not self._set_clipboard(text):
            return False, "Zwischenablage konnte nicht gesetzt werden. " + _INSTALL_HINT

        time.sleep(0.15)  # Clipboard-Owner braucht einen Moment

        ok, hint = True, ""
        if shutil.which("xdotool"):
            try:
                subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                               check=True, timeout=5, capture_output=True)
            except Exception as e:
                ok = False
                hint = ("Automatisches Einfuegen fehlgeschlagen ({}). "
                        "Text liegt in der Zwischenablage - mit Strg+V einfuegen.".format(e))
        else:
            ok = False
            hint = ("xdotool fehlt - Text liegt in der Zwischenablage, "
                    "mit Strg+V einfuegen. " + _INSTALL_HINT)

        if previous is not None and ok:
            # Alte Zwischenablage nach dem Einfuegen wiederherstellen
            def restore():
                time.sleep(0.6)
                self._set_clipboard(previous)
            threading.Thread(target=restore, daemon=True).start()

        return ok, hint
