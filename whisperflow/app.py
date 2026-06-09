# -*- coding: utf-8 -*-
"""Whisper Flow - Orchestrierung.

Verdrahtet Zustandsmaschine, Audio, Transkription, Woerterbuch, Statistik,
Hotkeys, Injection und die Qt-UI. Alle UI-Updates aus Worker-Threads
laufen ueber Qt-Signale (UiBridge) im GUI-Thread.

Threading-Modell:
  - GUI-Thread: Qt-Eventloop (Tray, Overlay, Dialoge)
  - PortAudio-Callback-Thread: fuellt den Audio-Puffer
  - Streaming-Worker: VAD + Transkription im Live-Modus
  - Finish-Worker: Abschluss-Transkription nach Aufnahme-Ende
  - Hotkey-Threads (pynput/evdev) + Hold-Timer

Die fruehere Absturzursache - Transkription blockierte den
Hotkey-Listener-Thread - ist damit behoben.
"""

import signal
import sys
import threading
import time

from whisperflow import __version__
from whisperflow.config import Config, safe_print
from whisperflow.state import AppState, StateInfo, StateMachine


def _qt():
    """Lazy-Import der Qt-Klassen (haelt Tests Qt-frei)."""
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication
    return QObject, QTimer, Signal, QApplication


class WhisperFlowApp:
    def __init__(self, qapp):
        from PySide6.QtCore import QObject, Signal

        self.qapp = qapp
        self.config = Config()
        self.state = StateMachine()

        from whisperflow.dictionary import UserDictionary
        from whisperflow.history import HistoryStore
        from whisperflow.stats import StatsTracker
        self.dictionary = UserDictionary(
            learn_threshold=int(self.config.get("dictionary_learn_threshold")))
        self.history = HistoryStore()
        self.stats = StatsTracker(typing_wpm=float(self.config.get("typing_wpm")))

        from whisperflow.transcribe.service import TranscriptionService
        self.service = TranscriptionService(self.config, self.dictionary)

        from whisperflow.audio.capture import AudioRecorder
        self.recorder = AudioRecorder(level_callback=self._on_audio_level)

        from whisperflow.inject import get_injector
        self.injector = get_injector(self.config)
        safe_print("[INJECT] Backend: {}".format(self.injector.name))

        # UI-Bruecke: Signale fuer thread-sichere UI-Updates
        class UiBridge(QObject):
            state_changed = Signal(object)
            level = Signal(float)
            live_text = Signal(str, str)
            overlay_recording = Signal(bool)
            overlay_processing = Signal()
            overlay_hide = Signal()
            notify = Signal(str, str, bool)
            stats_changed = Signal()

        self.bridge = UiBridge()

        from whisperflow.ui.overlay import RecordingOverlay
        from whisperflow.ui.tray import TrayUI
        self.overlay = RecordingOverlay()
        self.tray = TrayUI(self)

        self.bridge.state_changed.connect(self._on_state_changed_ui)
        self.bridge.level.connect(self.overlay.set_level)
        self.bridge.live_text.connect(self.overlay.set_live_text)
        self.bridge.overlay_recording.connect(self.overlay.show_recording)
        self.bridge.overlay_processing.connect(self.overlay.show_processing)
        self.bridge.overlay_hide.connect(self.overlay.hide_overlay)
        self.bridge.notify.connect(self.tray.notify)
        self.bridge.stats_changed.connect(self.tray.refresh_stats_label)
        self.state.add_listener(self.bridge.state_changed.emit)

        # Hotkeys
        from whisperflow.hotkeys import create_hotkey_backend
        from whisperflow.hotkeys.base import HotkeyPermissionError
        from whisperflow.hotkeys.controller import TriggerController
        self.controller = TriggerController(
            self.config,
            on_start=self.start_dictation,
            on_stop=self.stop_dictation,
            can_start=self._can_start,
            is_recording=lambda: self.state.state == AppState.RECORDING)
        self.hotkey_warning = ""
        try:
            self.hotkey_backend, self.hotkey_warning = create_hotkey_backend(
                self.config,
                on_press=self.controller.on_trigger_press,
                on_release=self.controller.on_trigger_release)
        except HotkeyPermissionError as e:
            self.hotkey_backend = None
            self.hotkey_warning = "{} {}".format(e, e.hint)

        # Laufende Diktat-Session
        self._streaming = None
        self._session_finals = []
        self._paused = False
        self._history_window = None

    # ------------------------------------------------------------------ Start

    def start(self):
        if self.hotkey_backend is not None:
            try:
                self.hotkey_backend.set_triggers(self.config.get("trigger_keys"))
                self.hotkey_backend.start()
                safe_print("[HOTKEYS] Backend: {}".format(self.hotkey_backend.name))
            except Exception as e:
                self.state.error("Hotkeys konnten nicht gestartet werden",
                                 hint=str(e))
        else:
            self.state.error("Keine globalen Hotkeys verfuegbar",
                             hint=self.hotkey_warning)

        if self.hotkey_warning:
            self.bridge.notify.emit("Hinweis", self.hotkey_warning, False)

        threading.Thread(target=self._load_model, name="wf-load", daemon=True).start()

        from whisperflow.hotkeys.base import display_name
        triggers = ", ".join(display_name(t) for t in self.config.get("trigger_keys"))
        safe_print("[BEREIT] Whisper Flow {} gestartet".format(__version__))
        safe_print("         Trigger: {} (gedrueckt halten zum Diktieren)".format(triggers))

    def _load_model(self):
        self.state.transition(AppState.LOADING, "Lade Modell...")
        ok = self.service.load()
        if ok:
            if self._paused:
                self.state.transition(AppState.PAUSED)
            else:
                self.state.transition(
                    AppState.READY, "Bereit ({})".format(self.service.device_label))
            if self.service.load_hint:
                self.bridge.notify.emit("Hinweis", self.service.load_hint, False)
            else:
                self.bridge.notify.emit(
                    "Bereit", "{} - Taste gedrueckt halten zum Diktieren".format(
                        self.service.describe()), False)
        else:
            self.state.error(self.service.load_error or "Modell laden fehlgeschlagen",
                             hint=self.service.load_hint)

    # ------------------------------------------------------------- Diktat-Flow

    def _can_start(self) -> bool:
        if self._paused:
            return False
        if not self.service.loaded:
            safe_print("[WARNUNG] Modell wird noch geladen...")
            return False
        return self.state.is_in(AppState.READY, AppState.ERROR)

    def start_dictation(self):
        """Startet die Aufnahme (aus Hotkey-/Timer-Thread aufrufbar)."""
        if not self._can_start():
            return
        if not self.state.transition(AppState.RECORDING):
            return

        from whisperflow.audio.capture import AudioCaptureError
        from whisperflow.audio.devices import find_device_index

        try:
            device_index = find_device_index(self.config.get("input_device"))
            self.recorder.start(device_index)
        except AudioCaptureError as e:
            self.state.error(str(e), hint=e.hint)
            self.bridge.notify.emit("Audio-Fehler", "{}\n{}".format(e, e.hint), True)
            return
        except Exception as e:
            self.state.error("Aufnahme fehlgeschlagen: {}".format(e),
                             hint="Mikrofon/Audiogeraet pruefen.")
            return

        self._session_finals = []
        live = self.config.get("mode") == "live"
        if live:
            from whisperflow.transcribe.streaming import StreamingTranscriber
            self._streaming = StreamingTranscriber(
                self.recorder, self.service, self.config,
                on_partial=self._on_partial_text,
                on_final=self._on_final_segment,
                on_error=self._on_streaming_error)
            self._streaming.start()

        if self.config.get("show_overlay"):
            self.bridge.overlay_recording.emit(live)
        safe_print("[AUFNAHME] Spreche jetzt...")

    def stop_dictation(self):
        """Stoppt die Aufnahme und transkribiert (nicht-blockierend)."""
        if not self.state.is_in(AppState.RECORDING):
            return
        self.state.transition(AppState.PROCESSING)
        self.bridge.overlay_processing.emit()
        threading.Thread(target=self._finish_dictation, name="wf-finish",
                         daemon=True).start()

    def _finish_dictation(self):
        try:
            speech_seconds = self.recorder.duration_s
            self.recorder.stop()
            t0 = time.time()

            if self._streaming is not None:
                streaming, self._streaming = self._streaming, None
                streaming.stop_and_flush()
                text = " ".join(streaming.finals).strip()
                if text and self.config.get("live_inject") == "end":
                    self._inject(text)
            else:
                audio = self.recorder.get_all()
                if audio.size < int(0.3 * 16000):
                    safe_print("[LEER] Keine Audiodaten aufgenommen")
                    self._end_session(None, 0, 0)
                    return
                text = self.service.transcribe(audio)
                if text:
                    self._inject(text)
                    preview = text[:60] + "..." if len(text) > 60 else text
                    self.bridge.notify.emit("Transkribiert", preview, False)

            processing_seconds = time.time() - t0
            self._end_session(text, speech_seconds, processing_seconds)
        except Exception as e:
            safe_print("[FEHLER] Transkription fehlgeschlagen: {}".format(e))
            import traceback
            traceback.print_exc()
            self.bridge.overlay_hide.emit()
            self.state.error("Transkription fehlgeschlagen: {}".format(e),
                             hint="Details im Terminal. Backend/Modell in den "
                                  "Einstellungen pruefen.")
            self.bridge.notify.emit("Fehler", str(e), True)

    def _end_session(self, text, speech_seconds, processing_seconds):
        self.bridge.overlay_hide.emit()
        if text:
            safe_print("[TEXT] {}".format(text))
            self.history.add(text)
            if self.config.get("stats_enabled"):
                from whisperflow.stats import count_words
                self.stats.record(count_words(text), speech_seconds, processing_seconds)
                self.bridge.stats_changed.emit()
        else:
            safe_print("[LEER] Keine Sprache erkannt")
        self.state.transition(
            AppState.READY, "Bereit ({})".format(self.service.device_label))

    # -- Live-Callbacks (Streaming-Worker-Thread) ------------------------------

    def _on_partial_text(self, text):
        tail = self._session_finals[-1] if self._session_finals else ""
        self.bridge.live_text.emit(tail[-120:], text)

    def _on_final_segment(self, text):
        first = not self._session_finals
        self._session_finals.append(text)
        if self.config.get("live_inject") == "segment":
            # Folgesegmente mit fuehrendem Leerzeichen anschliessen
            self._inject(text if first else " " + text)
        self.bridge.live_text.emit(text[-120:], "")

    def _on_streaming_error(self, message, hint):
        self.bridge.notify.emit("Live-Transkription", "{}\n{}".format(message, hint), True)

    def _inject(self, text):
        ok, hint = self.injector.inject(text)
        if not ok:
            self.bridge.notify.emit("Einfuegen", hint, True)

    def _on_audio_level(self, level):
        self.bridge.level.emit(level)

    # ----------------------------------------------------------------- UI-Slots

    def _on_state_changed_ui(self, info: StateInfo):
        self.tray.update_state(info)
        if info.state == AppState.ERROR:
            message = info.message or "Unbekannter Fehler"
            if info.hint:
                message += "\nLoesung: {}".format(info.hint)
            self.tray.notify("Fehler", message, error=True)

    def toggle_pause(self):
        if self.state.is_in(AppState.RECORDING, AppState.PROCESSING):
            return
        self._paused = not self._paused
        if self._paused:
            self.state.transition(AppState.PAUSED)
        else:
            self.state.transition(
                AppState.READY, "Bereit ({})".format(self.service.device_label)
                if self.service.loaded else "")
        self.tray.update_pause_label(self._paused)
        self.controller.cancel()

    def toggle_mode(self):
        new_mode = "batch" if self.config.get("mode") == "live" else "live"
        self.config.set("mode", new_mode)
        self.tray.refresh_mode_label()
        label = ("Live-Transkription" if new_mode == "live"
                 else "Batch-Modus (Transkription nach Aufnahme-Ende)")
        self.tray.notify("Modus", label)

    def show_settings(self):
        from whisperflow.ui.settings import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec()

    def show_history(self):
        from whisperflow.ui.history import HistoryWindow
        if self._history_window is None:
            self._history_window = HistoryWindow(self)
        self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()

    def on_user_correction(self, original, corrected):
        """Korrektur aus dem Verlaufsfenster -> Woerterbuch-Lernen."""
        if not self.config.get("dictionary_learning_enabled"):
            return []
        return self.dictionary.observe_correction(original, corrected)

    def reinject_text(self, text):
        threading.Thread(target=self._inject, args=(text,), daemon=True).start()

    def notify(self, title, message):
        self.tray.notify(title, message)

    def apply_settings(self, model_changed=False):
        """Uebernimmt geaenderte Einstellungen zur Laufzeit."""
        self.dictionary.learn_threshold = max(
            1, int(self.config.get("dictionary_learn_threshold")))
        self.stats.typing_wpm = float(self.config.get("typing_wpm"))
        if self.hotkey_backend is not None:
            try:
                self.hotkey_backend.set_triggers(self.config.get("trigger_keys"))
            except Exception as e:
                safe_print("[HOTKEYS] Trigger-Update fehlgeschlagen: {}".format(e))
        self.tray.refresh_mode_label()
        self.tray.refresh_stats_label()
        if model_changed:
            threading.Thread(target=self._reload_model, name="wf-reload",
                             daemon=True).start()
        self.tray.notify("Einstellungen", "Einstellungen gespeichert")

    def _reload_model(self):
        self.state.transition(AppState.LOADING, "Lade Modell neu...")
        ok = self.service.reload()
        if ok:
            self.state.transition(
                AppState.READY, "Bereit ({})".format(self.service.device_label))
        else:
            self.state.error(self.service.load_error or "Modell laden fehlgeschlagen",
                             hint=self.service.load_hint)

    # --------------------------------------------------------------------- Ende

    def quit(self):
        safe_print("\nBeende Whisper Flow...")
        try:
            self.controller.cancel()
            if self.hotkey_backend is not None:
                self.hotkey_backend.stop()
            if self._streaming is not None:
                self._streaming.stop_and_flush(timeout=2.0)
            self.recorder.stop()
            self.overlay.hide_overlay()
            self.tray.hide()
        except Exception:
            pass
        self.qapp.quit()


def main():
    QObject, QTimer, Signal, QApplication = _qt()

    QApplication.setQuitOnLastWindowClosed(False)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("Whisper Flow")

    # Nur eine Instanz (Autostart + manueller Start)
    from PySide6.QtCore import QDir, QLockFile
    lock = QLockFile(QDir.temp().absoluteFilePath("whisper-flow.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        safe_print("Whisper Flow laeuft bereits.")
        return 0

    from whisperflow.ui.icons import app_icon
    qapp.setWindowIcon(app_icon())

    app = WhisperFlowApp(qapp)

    # SIGINT/SIGTERM sauber behandeln: Timer laesst den Python-Interpreter
    # regelmaessig laufen, damit Signal-Handler greifen (Qt blockiert sonst in C)
    signal.signal(signal.SIGINT, lambda s, f: app.quit())
    signal.signal(signal.SIGTERM, lambda s, f: app.quit())
    wake_timer = QTimer()
    wake_timer.timeout.connect(lambda: None)
    wake_timer.start(250)

    app.start()
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
