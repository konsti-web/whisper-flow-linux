# -*- coding: utf-8 -*-
"""Hotkey-Backend ueber evdev: liest /dev/input direkt.

Funktioniert unter X11 UND Wayland (distro-unabhaengig), braucht aber
Leserechte auf /dev/input - ueblicherweise Mitgliedschaft in der Gruppe
'input':  sudo usermod -aG input $USER  (danach neu anmelden).
"""

import select
import threading
import time
from typing import Callable, List

from whisperflow.config import safe_print
from whisperflow.hotkeys.base import HotkeyBackend, HotkeyPermissionError

_PERMISSION_HINT = ("Fuer globale Hotkeys unter Wayland: "
                    "sudo usermod -aG input $USER  und neu anmelden. "
                    "Alternativ in den Einstellungen hotkey_backend=pynput setzen (nur X11).")

# pynput-Tastennamen -> evdev-Keycodes
_NAME_TO_EVDEV = {
    "alt_gr": "KEY_RIGHTALT", "alt_l": "KEY_LEFTALT", "alt_r": "KEY_RIGHTALT",
    "alt": "KEY_LEFTALT",
    "ctrl_l": "KEY_LEFTCTRL", "ctrl_r": "KEY_RIGHTCTRL", "ctrl": "KEY_LEFTCTRL",
    "shift_l": "KEY_LEFTSHIFT", "shift_r": "KEY_RIGHTSHIFT", "shift": "KEY_LEFTSHIFT",
    "cmd_l": "KEY_LEFTMETA", "cmd_r": "KEY_RIGHTMETA", "cmd": "KEY_LEFTMETA",
    "space": "KEY_SPACE", "tab": "KEY_TAB", "caps_lock": "KEY_CAPSLOCK",
    "scroll_lock": "KEY_SCROLLLOCK", "print_screen": "KEY_SYSRQ", "pause": "KEY_PAUSE",
    "insert": "KEY_INSERT", "delete": "KEY_DELETE", "home": "KEY_HOME", "end": "KEY_END",
    "page_up": "KEY_PAGEUP", "page_down": "KEY_PAGEDOWN",
    "num_lock": "KEY_NUMLOCK", "menu": "KEY_COMPOSE", "esc": "KEY_ESC",
    "enter": "KEY_ENTER", "backspace": "KEY_BACKSPACE",
}
for _i in range(1, 13):
    _NAME_TO_EVDEV["f{}".format(_i)] = "KEY_F{}".format(_i)

# Bekannte X11-Keysyms -> evdev (fuer migrierte Configs)
_VK_TO_EVDEV = {65027: "KEY_RIGHTALT"}

# Maustasten
_MOUSE_TO_EVDEV = {
    "left": "BTN_LEFT", "right": "BTN_RIGHT", "middle": "BTN_MIDDLE",
    "button8": "BTN_SIDE", "button9": "BTN_EXTRA",
    "button10": "BTN_FORWARD", "button11": "BTN_BACK",
}


def _to_code(name: str):
    from evdev import ecodes
    return ecodes.ecodes.get(name)


class EvdevHotkeyBackend(HotkeyBackend):
    name = "evdev"

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]):
        super().__init__(on_press, on_release)
        self._codes = set()          # Trigger-Keycodes
        self._combo_alt_space = False
        self._alt_down = False
        self._pressed_triggers = set()
        self._thread = None
        self._running = False
        self._rescan_at = 0.0

    def check_permissions(self):
        """Wirft HotkeyPermissionError, wenn keine Geraete lesbar sind."""
        import evdev
        paths = evdev.list_devices()
        if not paths:
            raise HotkeyPermissionError(
                "Keine Eingabegeraete lesbar (/dev/input).", hint=_PERMISSION_HINT)

    def set_triggers(self, triggers: List[str]):
        codes = set()
        combo = False
        for s in triggers or []:
            try:
                code = None
                if s.startswith("key:ev:"):
                    code = int(s[7:])
                elif s.startswith("key:vk:"):
                    name = _VK_TO_EVDEV.get(int(s[7:]))
                    if name:
                        code = _to_code(name)
                    else:
                        safe_print("[HOTKEYS] VK-Code {} ist unter evdev nicht abbildbar "
                                   "- Trigger in den Einstellungen neu erfassen.".format(s[7:]))
                elif s.startswith("key:char:"):
                    char = s[9:].strip().upper()
                    if len(char) == 1 and (char.isalpha() or char.isdigit()):
                        code = _to_code("KEY_{}".format(char))
                elif s.startswith("key:"):
                    name = _NAME_TO_EVDEV.get(s[4:])
                    if name:
                        code = _to_code(name)
                    else:
                        safe_print("[HOTKEYS] Taste '{}' unter evdev unbekannt.".format(s[4:]))
                elif s.startswith("mouse:"):
                    name = _MOUSE_TO_EVDEV.get(s[6:])
                    if name:
                        code = _to_code(name)
                elif s == "combo:alt+space":
                    combo = True
                if code is not None:
                    codes.add(code)
            except Exception as e:
                safe_print("[HOTKEYS] Trigger '{}' unlesbar: {}".format(s, e))
        self._codes = codes
        self._combo_alt_space = combo

    # -- Event-Schleife ---------------------------------------------------------

    def _open_devices(self):
        import evdev
        from evdev import ecodes
        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps:
                    devices.append(dev)
                else:
                    dev.close()
            except Exception:
                continue
        return devices

    def _loop(self):
        from evdev import ecodes

        devices = self._open_devices()
        if not devices:
            safe_print("[HOTKEYS] evdev: keine Geraete lesbar")
        alt_codes = {_to_code("KEY_LEFTALT"), _to_code("KEY_RIGHTALT")}
        space_code = _to_code("KEY_SPACE")
        self._rescan_at = time.time() + 10

        while self._running:
            # Periodisch neu scannen (Hotplug: Bluetooth-Tastaturen etc.)
            if time.time() >= self._rescan_at:
                for dev in devices:
                    try:
                        dev.close()
                    except Exception:
                        pass
                devices = self._open_devices()
                self._rescan_at = time.time() + 10

            if not devices:
                time.sleep(1.0)
                continue

            try:
                fd_map = {dev.fd: dev for dev in devices}
                readable, _, _ = select.select(list(fd_map), [], [], 0.5)
            except Exception:
                time.sleep(0.5)
                continue

            for fd in readable:
                dev = fd_map.get(fd)
                if dev is None:
                    continue
                try:
                    for event in dev.read():
                        if event.type != ecodes.EV_KEY or event.value == 2:
                            continue  # nur Press(1)/Release(0), kein Auto-Repeat
                        self._handle_key(event.code, event.value == 1,
                                         alt_codes, space_code)
                except OSError:
                    # Geraet entfernt - beim naechsten Rescan bereinigt
                    devices = [d for d in devices if d.fd != fd]
                except Exception:
                    pass

        for dev in devices:
            try:
                dev.close()
            except Exception:
                pass

    def _handle_key(self, code, pressed, alt_codes, space_code):
        is_trigger = code in self._codes
        if self._combo_alt_space:
            if code in alt_codes:
                self._alt_down = pressed
                if not pressed and "combo" in self._pressed_triggers:
                    is_trigger = False  # Release wird unten ueber combo behandelt
                    self._pressed_triggers.discard("combo")
                    self.on_release()
                    return
            elif code == space_code and self._alt_down:
                if pressed:
                    self._pressed_triggers.add("combo")
                    self.on_press()
                else:
                    self._pressed_triggers.discard("combo")
                    self.on_release()
                return

        if not is_trigger:
            return
        if pressed:
            self._pressed_triggers.add(code)
            self.on_press()
        else:
            self._pressed_triggers.discard(code)
            self.on_release()

    def start(self):
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="wf-evdev", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)

    # -- Erfassung -----------------------------------------------------------------

    def capture_once(self, callback: Callable[[str], None], timeout: float = 5.0):
        """Erfasst den naechsten Tastendruck (Esc bricht ab) in eigenem Thread."""
        def worker():
            from evdev import ecodes
            devices = self._open_devices()
            if not devices:
                callback(None)
                return
            esc = _to_code("KEY_ESC")
            ui_buttons = {_to_code("BTN_LEFT"), _to_code("BTN_RIGHT"), _to_code("BTN_MIDDLE")}
            deadline = time.time() + timeout
            result = None
            try:
                while time.time() < deadline and result is None:
                    fd_map = {dev.fd: dev for dev in devices}
                    readable, _, _ = select.select(list(fd_map), [], [], 0.25)
                    for fd in readable:
                        dev = fd_map.get(fd)
                        try:
                            for event in dev.read():
                                if event.type != ecodes.EV_KEY or event.value != 1:
                                    continue
                                if event.code == esc:
                                    result = ("cancel", None)
                                    break
                                if event.code in ui_buttons:
                                    continue
                                # Maustasten im bekannten Format serialisieren
                                rev = {_to_code(v): k for k, v in _MOUSE_TO_EVDEV.items()}
                                if event.code in rev:
                                    result = ("ok", "mouse:{}".format(rev[event.code]))
                                else:
                                    result = ("ok", "key:ev:{}".format(event.code))
                                break
                        except Exception:
                            continue
                        if result is not None:
                            break
            finally:
                for dev in devices:
                    try:
                        dev.close()
                    except Exception:
                        pass
            callback(result[1] if result and result[0] == "ok" else None)

        threading.Thread(target=worker, daemon=True).start()
