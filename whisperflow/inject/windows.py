# -*- coding: utf-8 -*-
"""Texteinfuegen unter Windows: Win32-Zwischenablage (ctypes) + Strg+V (pynput)."""

import time

from whisperflow.inject.base import TextInjector

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _set_clipboard_win32(text: str) -> bool:
    """Setzt die Zwischenablage ueber die Win32-API (nur Stdlib/ctypes)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    data = text.encode("utf-16-le") + b"\x00\x00"
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


class WindowsInjector(TextInjector):
    name = "windows"

    def _set_clipboard(self, text: str) -> bool:
        try:
            return _set_clipboard_win32(text)
        except Exception:
            # Fallback ueber PowerShell
            try:
                import subprocess
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                    input=text.encode("utf-8"), timeout=10, check=True)
                return True
            except Exception:
                return False

    def _inject(self, text: str):
        if not self._set_clipboard(text):
            return False, "Zwischenablage konnte nicht gesetzt werden."

        time.sleep(0.15)

        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            with kb.pressed(Key.ctrl):
                kb.press("v")
                kb.release("v")
            return True, ""
        except Exception as e:
            return False, ("Einfuegen fehlgeschlagen ({}). "
                           "Text liegt in der Zwischenablage - mit Strg+V einfuegen.".format(e))
