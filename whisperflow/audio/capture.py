# -*- coding: utf-8 -*-
"""Audioaufnahme ueber sounddevice (PortAudio) im Callback-Modus.

Der Callback-Modus ersetzt die alte blockierende PyAudio-read()-Schleife.
Damit entfaellt die Race-Condition beim Stoppen (Stream wurde geschlossen,
waehrend der Lese-Thread noch in read() hing - ein Absturzkandidat).
"""

import threading
from typing import Callable, Optional

import numpy as np

TARGET_RATE = 16000  # Whisper erwartet 16 kHz mono


class AudioCaptureError(Exception):
    """Aufnahme konnte nicht gestartet werden (mit Loesungshinweis)."""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


def resample_to_16k(audio: np.ndarray, source_rate: int) -> np.ndarray:
    """Lineares Resampling auf 16 kHz (ausreichend fuer Sprache)."""
    if source_rate == TARGET_RATE or audio.size == 0:
        return audio
    duration = audio.shape[0] / float(source_rate)
    target_length = max(1, int(duration * TARGET_RATE))
    indices = np.linspace(0, audio.shape[0] - 1, target_length)
    return np.interp(indices, np.arange(audio.shape[0]), audio).astype(np.float32)


class AudioRecorder:
    """Nimmt Audio auf und stellt es als float32 @ 16 kHz bereit.

    read_new() liefert nur die seit dem letzten Aufruf neuen Samples
    (fuer die Live-Transkription), get_all() die komplette Aufnahme
    (fuer den Batch-Modus). Beide sind auch nach stop() noch gueltig.
    """

    def __init__(self, level_callback: Optional[Callable[[float], None]] = None):
        self._lock = threading.Lock()
        self._frames = []          # list[np.ndarray int16] in Aufnahme-Reihenfolge
        self._consumed = 0         # Index fuer read_new()
        self._stream = None
        self._level_cb = level_callback
        self.sample_rate = TARGET_RATE
        self._recording = False

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self, device_index: Optional[int] = None):
        if self._recording:
            return
        with self._lock:
            self._frames = []
            self._consumed = 0

        import sounddevice as sd

        last_error = None
        for rate in self._candidate_rates(device_index):
            try:
                stream = sd.InputStream(
                    samplerate=rate, channels=1, dtype="int16",
                    device=device_index, blocksize=1024,
                    callback=self._callback)
                stream.start()
                self._stream = stream
                self.sample_rate = rate
                if rate != TARGET_RATE:
                    from whisperflow.config import safe_print
                    safe_print("[INFO] 16 kHz nicht unterstuetzt, nehme mit {} Hz auf".format(rate))
                self._recording = True
                return
            except Exception as e:
                last_error = e

        raise AudioCaptureError(
            "Aufnahme konnte nicht gestartet werden: {}".format(last_error),
            hint=("Mikrofon angeschlossen und in den Systemeinstellungen erlaubt? "
                  "Anderes Eingabegeraet in den Einstellungen waehlen."))

    def _candidate_rates(self, device_index):
        """16 kHz zuerst, dann die native Rate des Geraets als Fallback."""
        rates = [TARGET_RATE]
        try:
            import sounddevice as sd
            if device_index is not None:
                info = sd.query_devices(device_index)
            else:
                info = sd.query_devices(kind="input")
            native = int(info.get("default_samplerate") or 48000)
            if native not in rates:
                rates.append(native)
        except Exception:
            rates.append(48000)
        return rates

    def _callback(self, indata, frames, time_info, status):
        """Laeuft im PortAudio-Thread - nur puffern, nichts Blockierendes."""
        try:
            data = indata[:, 0].copy()
            with self._lock:
                if self._recording:
                    self._frames.append(data)
            if self._level_cb is not None:
                samples = data.astype(np.float32)
                rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
                self._level_cb(min(1.0, rms / 8000.0))
        except Exception:
            pass

    def stop(self):
        """Stoppt die Aufnahme. Gepufferte Daten bleiben lesbar."""
        self._recording = False
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def read_new(self) -> np.ndarray:
        """Neue Samples seit dem letzten Aufruf als float32 @ 16 kHz."""
        with self._lock:
            chunk = self._frames[self._consumed:]
            self._consumed = len(self._frames)
        if not chunk:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunk).astype(np.float32) / 32768.0
        return resample_to_16k(audio, self.sample_rate)

    def get_all(self) -> np.ndarray:
        """Komplette Aufnahme als float32 @ 16 kHz."""
        with self._lock:
            frames = list(self._frames)
        if not frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        return resample_to_16k(audio, self.sample_rate)

    @property
    def duration_s(self) -> float:
        with self._lock:
            samples = sum(f.shape[0] for f in self._frames)
        return samples / float(self.sample_rate) if samples else 0.0
