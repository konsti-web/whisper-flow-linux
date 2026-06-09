# -*- coding: utf-8 -*-
"""Live-Transkription: VAD-Chunking mit fortlaufender Vorschau.

Strategie (Begruendung der Architektur-Entscheidung):
  - Abgeschlossene Sprachsegmente (Pause erkannt) werden genau einmal
    transkribiert und sofort als final gemeldet -> stabiler Text, kein
    Flackern, Woerterbuch und Statistik greifen pro Segment.
  - Das noch offene Segment wird periodisch transkribiert und als
    vorlaeufige Vorschau gemeldet (erste Anzeige <= 2 s nach Sprechbeginn).
  - Alternative "LocalAgreement"-Streams (whisper_streaming) liefern
    fruehere Finals, transkribieren dasselbe Audio aber vielfach und sind
    deutlich komplexer; fuer Diktat mit natuerlichen Pausen ist
    VAD-Chunking robuster und ressourcenschonender.

Alles laeuft in einem einzigen Worker-Thread: Wenn die Hardware langsamer
als Echtzeit ist, fallen automatisch Vorschau-Updates aus (Backpressure),
finale Segmente gehen nie verloren.
"""

import threading
import time
from typing import Callable, List, Optional

from whisperflow.audio.vad import SegmenterConfig, StreamSegmenter
from whisperflow.config import safe_print


class StreamingTranscriber:
    def __init__(self, recorder, service, config,
                 on_partial: Callable[[str], None],
                 on_final: Callable[[str], None],
                 on_error: Callable[[str, str], None]):
        self.recorder = recorder
        self.service = service
        self.config = config
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_error = on_error

        self.segmenter = StreamSegmenter(SegmenterConfig(
            threshold=float(config.get("vad_threshold")),
            silence_ms=int(config.get("vad_silence_ms")),
            max_segment_s=float(config.get("max_segment_s")),
        ))
        self.preview_interval = float(config.get("live_preview_interval"))
        self.finals: List[str] = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_preview_at = 0.0
        self._last_preview_len = 0

    def start(self):
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="wf-streaming", daemon=True)
        self._thread.start()

    def stop_and_flush(self, timeout: float = 120.0):
        """Beendet den Worker und verarbeitet das restliche Audio (blockierend)."""
        self._running = False
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=timeout)

    # -- intern -----------------------------------------------------------

    def _transcribe_final(self, segment):
        try:
            text = self.service.transcribe(segment, is_stream_segment=True)
        except Exception as e:
            self.on_error("Transkription fehlgeschlagen: {}".format(e),
                          "Modell/Backend in den Einstellungen pruefen.")
            return
        if text:
            self.finals.append(text)
            self.on_final(text)

    def _maybe_preview(self):
        now = time.time()
        if now - self._last_preview_at < self.preview_interval:
            return
        current = self.segmenter.current()
        # Vorschau erst ab ~0,5 s Audio und nur wenn neues Material da ist
        if current is None or current.shape[0] < int(0.5 * 16000):
            return
        if current.shape[0] == self._last_preview_len:
            return
        self._last_preview_at = now
        self._last_preview_len = current.shape[0]
        try:
            text = self.service.transcribe(current, is_stream_segment=True)
        except Exception:
            return  # Vorschau-Fehler sind unkritisch, Finals melden Fehler
        if text:
            self.on_partial(text)

    def _loop(self):
        try:
            while self._running:
                audio = self.recorder.read_new()
                if audio.size:
                    for segment in self.segmenter.feed(audio):
                        self.on_partial("")  # Vorschau leeren, Segment wird final
                        self._transcribe_final(segment)
                        self._last_preview_len = 0
                self._maybe_preview()
                time.sleep(0.05)

            # Aufnahme beendet: Restdaten verarbeiten
            audio = self.recorder.read_new()
            for segment in self.segmenter.feed(audio):
                self._transcribe_final(segment)
            tail = self.segmenter.flush()
            if tail is not None:
                self._transcribe_final(tail)
        except Exception as e:
            safe_print("[STREAMING] Unerwarteter Fehler: {}".format(e))
            self.on_error("Live-Transkription abgebrochen: {}".format(e),
                          "Batch-Modus in den Einstellungen als Ausweich-Option nutzen.")
