# -*- coding: utf-8 -*-
"""Hold-to-Record- und Doppel-Tipp-Logik, unabhaengig vom Hotkey-Backend.

Portiert aus der GTK-Version; die Logik ist unveraendert:
  - Trigger gedrueckt halten (>= hold_threshold) -> Aufnahme bis zum Loslassen
  - Doppel-Tipp (optional) -> freihaendige Aufnahme, Doppel-Tipp stoppt
"""

import threading
import time
from typing import Callable


class TriggerController:
    def __init__(self, config,
                 on_start: Callable[[], None],
                 on_stop: Callable[[], None],
                 can_start: Callable[[], bool],
                 is_recording: Callable[[], bool]):
        self.config = config
        self.on_start = on_start
        self.on_stop = on_stop
        self.can_start = can_start
        self.is_recording = is_recording

        self._lock = threading.Lock()
        self._key_pressed = False
        self._hold_timer = None
        self._recording_started_by_hold = False
        self._double_tap_recording = False
        self._last_release_time = 0.0

    def _start_after_hold(self):
        with self._lock:
            if not self._key_pressed or self.is_recording():
                return
            if not self.can_start():
                return
            self._recording_started_by_hold = True
        self.on_start()

    def on_trigger_press(self):
        with self._lock:
            if self._key_pressed:
                return
            self._key_pressed = True
            if self._hold_timer is not None:
                self._hold_timer.cancel()
            self._hold_timer = threading.Timer(
                float(self.config.get("hold_threshold")), self._start_after_hold)
            self._hold_timer.daemon = True
            self._hold_timer.start()

    def on_trigger_release(self):
        with self._lock:
            self._key_pressed = False
            if self._hold_timer is not None:
                self._hold_timer.cancel()
                self._hold_timer = None

            now = time.time()
            double_tap_enabled = bool(self.config.get("double_tap_enabled"))
            interval = float(self.config.get("double_tap_interval") or 0.4)
            recording = self.is_recording()

            action = None
            if recording and self._recording_started_by_hold:
                self._recording_started_by_hold = False
                action = "stop"
            elif recording and self._double_tap_recording:
                if now - self._last_release_time < interval:
                    self._double_tap_recording = False
                    action = "stop"
            elif not recording and double_tap_enabled:
                if now - self._last_release_time < interval and self.can_start():
                    self._double_tap_recording = True
                    action = "start"

            self._last_release_time = now

        if action == "stop":
            self.on_stop()
        elif action == "start":
            self.on_start()

    def cancel(self):
        with self._lock:
            if self._hold_timer is not None:
                self._hold_timer.cancel()
                self._hold_timer = None
            self._key_pressed = False
            self._recording_started_by_hold = False
            self._double_tap_recording = False
