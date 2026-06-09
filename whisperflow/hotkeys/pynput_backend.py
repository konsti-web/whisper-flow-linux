# -*- coding: utf-8 -*-
"""Hotkey-Backend ueber pynput (X11, macOS, Windows).

Hinweis macOS: pynput braucht die Berechtigung "Eingabeueberwachung"
(Systemeinstellungen > Datenschutz & Sicherheit).
"""

import threading
from typing import Callable, List

from whisperflow.config import safe_print
from whisperflow.hotkeys.base import HotkeyBackend


def serialize_keyboard_key(key) -> str:
    """Serialisiert einen pynput-Key ins Trigger-Format."""
    from pynput import keyboard
    if isinstance(key, keyboard.Key):
        return "key:{}".format(key.name)
    if isinstance(key, keyboard.KeyCode):
        if key.vk is not None:
            return "key:vk:{}".format(key.vk)
        if key.char is not None:
            return "key:char:{}".format(key.char)
    return ""


class PynputHotkeyBackend(HotkeyBackend):
    name = "pynput"

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]):
        super().__init__(on_press, on_release)
        self._keyboard_triggers = set()
        self._mouse_triggers = set()
        self._has_alt_space_combo = False
        self._alt_pressed = False
        self._kb_listener = None
        self._mouse_listener = None

    def set_triggers(self, triggers: List[str]):
        from pynput import keyboard, mouse

        kb_set, mouse_set = set(), set()
        combo = False
        for s in triggers or []:
            try:
                if s.startswith("key:vk:"):
                    kb_set.add(keyboard.KeyCode.from_vk(int(s[7:])))
                elif s.startswith("key:char:"):
                    kb_set.add(keyboard.KeyCode.from_char(s[9:]))
                elif s.startswith("key:ev:"):
                    # evdev-Code aus Wayland-Erfassung - hier nicht abbildbar
                    safe_print("[HOTKEYS] Trigger '{}' ist ein evdev-Code und wird "
                               "vom pynput-Backend ignoriert (Trigger neu erfassen).".format(s))
                elif s.startswith("key:"):
                    name = s[4:]
                    try:
                        kb_set.add(keyboard.Key[name])
                    except KeyError:
                        safe_print("[HOTKEYS] Unbekannte Taste: {}".format(name))
                elif s.startswith("mouse:"):
                    btn_name = s[6:]
                    try:
                        mouse_set.add(mouse.Button[btn_name])
                    except KeyError:
                        safe_print("[HOTKEYS] Unbekannte Maustaste: {}".format(btn_name))
                elif s == "combo:alt+space":
                    combo = True
            except Exception as e:
                safe_print("[HOTKEYS] Trigger '{}' unlesbar: {}".format(s, e))

        self._keyboard_triggers = kb_set
        self._mouse_triggers = mouse_set
        self._has_alt_space_combo = combo
        # Mouse-Listener nur bei Bedarf (neu) starten
        if self._kb_listener is not None:
            self._restart_mouse_listener()

    # -- Listener ------------------------------------------------------------

    def _on_key_press(self, key):
        try:
            from pynput import keyboard
            is_trigger = False
            if self._has_alt_space_combo:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._alt_pressed = True
                elif key == keyboard.Key.space and self._alt_pressed:
                    is_trigger = True
            if key in self._keyboard_triggers:
                is_trigger = True
            if is_trigger:
                self.on_press()
        except Exception:
            pass

    def _on_key_release(self, key):
        try:
            from pynput import keyboard
            is_release = False
            if self._has_alt_space_combo:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._alt_pressed = False
                    is_release = True
                elif key == keyboard.Key.space:
                    is_release = True
            if key in self._keyboard_triggers:
                is_release = True
            if is_release:
                self.on_release()
        except Exception:
            pass

    def _on_mouse_click(self, x, y, button, pressed):
        try:
            if button not in self._mouse_triggers:
                return
            if pressed:
                self.on_press()
            else:
                self.on_release()
        except Exception:
            pass

    def _restart_mouse_listener(self):
        from pynput import mouse
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None
        if self._mouse_triggers:
            self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
            self._mouse_listener.start()

    def start(self):
        from pynput import keyboard
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press, on_release=self._on_key_release)
        self._kb_listener.start()
        self._restart_mouse_listener()

    def stop(self):
        for listener in (self._kb_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._kb_listener = None
        self._mouse_listener = None

    # -- Erfassung -------------------------------------------------------------

    def capture_once(self, callback: Callable[[str], None], timeout: float = 5.0):
        """Erfasst die naechste Taste/Seitentaste (Esc bricht ab)."""
        from pynput import keyboard, mouse

        state = {"done": False}
        listeners = []

        def finish(serialized):
            if state["done"]:
                return
            state["done"] = True
            for lst in listeners:
                try:
                    lst.stop()
                except Exception:
                    pass
            callback(serialized)

        def on_key(key):
            if key == keyboard.Key.esc:
                finish(None)
                return False
            serialized = serialize_keyboard_key(key)
            if serialized:
                finish(serialized)
            return False

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            if button in (mouse.Button.left, mouse.Button.right, mouse.Button.middle):
                return  # UI-Interaktion nicht als Trigger erfassen
            finish("mouse:{}".format(button.name))
            return False

        kb = keyboard.Listener(on_press=on_key)
        ms = mouse.Listener(on_click=on_click)
        listeners.extend([kb, ms])
        kb.start()
        ms.start()

        def timeout_guard():
            finish(None)

        timer = threading.Timer(timeout, timeout_guard)
        timer.daemon = True
        timer.start()
