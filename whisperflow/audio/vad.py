# -*- coding: utf-8 -*-
"""Energie-basierte Sprach-Segmentierung fuer die Live-Transkription.

Entscheidung: Energie-VAD statt Silero-VAD fuer das Chunking.
  + keine Zusatzabhaengigkeit, funktioniert mit jedem Backend
  + deterministisch und damit sauber unit-testbar
  + fuer Pausen-Erkennung beim Diktat voellig ausreichend
  - weniger praezise bei Hintergrundgeraeuschen; dafuer filtert die
    Transkription selbst noch einmal (faster-whisper vad_filter im
    Batch-Modus) und der Schwellwert passt sich dem Grundrauschen an.
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

FRAME_MS = 30  # Analyse-Fenster


@dataclass
class SegmenterConfig:
    sample_rate: int = 16000
    threshold: float = 0.006      # RMS-Grundschwelle (float32-Audio)
    silence_ms: int = 600         # Stille, bis ein Segment finalisiert wird
    min_speech_ms: int = 250      # kuerzere Bursts werden verworfen
    max_segment_s: float = 15.0   # Zwangs-Split sehr langer Segmente
    pre_roll_ms: int = 240        # Audio vor Sprachbeginn mitnehmen
    trailing_silence_ms: int = 300  # Stille am Segmentende behalten (Kontext)
    adaptive: bool = True         # Schwelle ans Grundrauschen anpassen


class StreamSegmenter:
    """Verarbeitet fortlaufend Audio und liefert abgeschlossene Sprachsegmente.

    feed(audio)  -> Liste abgeschlossener Segmente (np.ndarray float32 @ 16 kHz)
    current()    -> offenes (vorlaeufiges) Segment oder None
    flush()      -> Rest-Segment bei Aufnahme-Ende oder None
    """

    def __init__(self, config: Optional[SegmenterConfig] = None):
        self.cfg = config or SegmenterConfig()
        self._frame_len = int(self.cfg.sample_rate * FRAME_MS / 1000)
        self._pending = np.zeros(0, dtype=np.float32)  # unverarbeitete Samples
        self._pre_roll: List[np.ndarray] = []
        self._pre_roll_frames = max(1, self.cfg.pre_roll_ms // FRAME_MS)
        self._segment: List[np.ndarray] = []
        self._in_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._noise_floor = 0.0

    # -- intern ------------------------------------------------------------

    def _effective_threshold(self) -> float:
        if self.cfg.adaptive and self._noise_floor > 0:
            return max(self.cfg.threshold, self._noise_floor * 2.5)
        return self.cfg.threshold

    def _finalize(self, *, forced: bool) -> Optional[np.ndarray]:
        """Schliesst das offene Segment ab; None wenn zu kurz."""
        if not self._segment:
            return None
        segment = np.concatenate(self._segment)
        self._segment = []
        self._in_speech = False

        keep_silence = int(self.cfg.sample_rate * self.cfg.trailing_silence_ms / 1000)
        trailing = self._silence_frames * self._frame_len
        if not forced and trailing > keep_silence:
            segment = segment[: max(1, segment.shape[0] - (trailing - keep_silence))]
        self._silence_frames = 0

        speech_ms = self._speech_frames * FRAME_MS
        self._speech_frames = 0
        min_ms = 150 if forced else self.cfg.min_speech_ms
        if speech_ms < min_ms:
            return None
        return segment

    # -- API ---------------------------------------------------------------

    def feed(self, audio: np.ndarray) -> List[np.ndarray]:
        """Nimmt neue Samples entgegen, gibt abgeschlossene Segmente zurueck."""
        finished: List[np.ndarray] = []
        if audio.size:
            self._pending = np.concatenate([self._pending, audio.astype(np.float32)])

        max_samples = int(self.cfg.max_segment_s * self.cfg.sample_rate)
        threshold = self._effective_threshold()

        while self._pending.shape[0] >= self._frame_len:
            frame = self._pending[: self._frame_len]
            self._pending = self._pending[self._frame_len:]
            rms = float(np.sqrt(np.mean(frame ** 2)))
            is_speech = rms > threshold

            if not self._in_speech:
                if is_speech:
                    # Sprachbeginn: Pre-Roll mitnehmen (weiche Wortanfaenge)
                    self._segment = list(self._pre_roll)
                    self._pre_roll = []
                    self._segment.append(frame)
                    self._in_speech = True
                    self._silence_frames = 0
                    self._speech_frames = 1
                else:
                    # Grundrauschen mitschaetzen (exponentielles Mittel)
                    self._noise_floor = (0.95 * self._noise_floor + 0.05 * rms
                                         if self._noise_floor > 0 else rms)
                    threshold = self._effective_threshold()
                    self._pre_roll.append(frame)
                    if len(self._pre_roll) > self._pre_roll_frames:
                        self._pre_roll.pop(0)
            else:
                self._segment.append(frame)
                if is_speech:
                    self._speech_frames += 1
                    self._silence_frames = 0
                else:
                    self._silence_frames += 1

                segment_samples = sum(f.shape[0] for f in self._segment)
                if self._silence_frames * FRAME_MS >= self.cfg.silence_ms:
                    seg = self._finalize(forced=False)
                    if seg is not None:
                        finished.append(seg)
                elif segment_samples >= max_samples:
                    # Zwangs-Split: Segment abschliessen, Sprache laeuft weiter
                    seg = self._finalize(forced=True)
                    if seg is not None:
                        finished.append(seg)
                    self._in_speech = True  # bleibt in Sprache, neues Segment
                    self._speech_frames = 1

        return finished

    def current(self) -> Optional[np.ndarray]:
        """Kopie des offenen Segments (fuer die Vorschau-Transkription)."""
        if not self._in_speech or not self._segment:
            return None
        return np.concatenate(self._segment)

    def flush(self) -> Optional[np.ndarray]:
        """Bei Aufnahme-Ende: Rest (inkl. unverarbeiteter Samples) abschliessen."""
        if self._pending.size:
            if self._in_speech:
                self._segment.append(self._pending)
            self._pending = np.zeros(0, dtype=np.float32)
        return self._finalize(forced=True)

    @property
    def in_speech(self) -> bool:
        return self._in_speech
