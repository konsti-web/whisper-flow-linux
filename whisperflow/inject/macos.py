# -*- coding: utf-8 -*-
"""Texteinfuegen unter macOS: pbcopy + osascript (Cmd+V).

Der Tastendruck via System Events braucht die Bedienungshilfen-Berechtigung;
ohne sie liefert osascript Fehler 1002 - der Hinweis erklaert den Fix.
"""

import subprocess
import time

from whisperflow.inject.base import TextInjector

_PERMISSION_HINT = ("Automatisches Einfuegen braucht eine Berechtigung: "
                    "Systemeinstellungen > Datenschutz & Sicherheit > Bedienungshilfen "
                    "> Whisper Flow (bzw. Terminal) erlauben. "
                    "Text liegt in der Zwischenablage - mit Cmd+V einfuegen.")


class MacInjector(TextInjector):
    name = "macos"

    def _set_clipboard(self, text: str) -> bool:
        try:
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"), timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    def _inject(self, text: str):
        if not self._set_clipboard(text):
            return False, "Zwischenablage konnte nicht gesetzt werden (pbcopy)."

        time.sleep(0.15)

        try:
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to keystroke "v" using command down'],
                check=True, timeout=5, capture_output=True)
            return True, ""
        except subprocess.CalledProcessError:
            return False, _PERMISSION_HINT
        except Exception as e:
            return False, "Einfuegen fehlgeschlagen ({}). {}".format(e, _PERMISSION_HINT)
