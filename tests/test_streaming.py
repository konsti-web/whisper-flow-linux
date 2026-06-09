# -*- coding: utf-8 -*-
"""Tests fuer die Streaming-Pipeline (Live-Transkription).

Mit Fake-Recorder und Fake-Service - kein Whisper, kein Audio-Geraet.
Regressionstest fuer das "wabelige" Overlay: Die Vorschau darf beim
Finalisieren eines Segments nicht geleert werden, und finale Segmente
muessen sich in Reihenfolge akkumulieren.
"""

import numpy as np

from whisperflow.config import Config
from whisperflow.transcribe.streaming import StreamingTranscriber

RATE = 16000


class FakeRecorder:
    """Liefert das komplette Audio im ersten read_new()-Aufruf."""

    def __init__(self, audio):
        self._audio = audio.astype(np.float32)
        self._given = False

    def read_new(self):
        if self._given:
            return np.zeros(0, dtype=np.float32)
        self._given = True
        return self._audio


class FakeService:
    """'Transkribiert' deterministisch anhand der Audiolaenge."""

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, is_stream_segment=False, apply_dictionary=True):
        self.calls.append(len(audio))
        return "seg-{:.0f}".format(round(len(audio) / RATE, 1) * 10)


def _tone(seconds, amplitude=0.1):
    t = np.linspace(0, seconds, int(RATE * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _silence(seconds):
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def _run_streaming(audio, tmp_path):
    config = Config(config_file=tmp_path / "config.json")
    partials, finals, errors = [], [], []
    streaming = StreamingTranscriber(
        FakeRecorder(audio), FakeService(), config,
        on_partial=partials.append,
        on_final=finals.append,
        on_error=lambda m, h: errors.append((m, h)))
    # start() + sofortiges stop_and_flush(): Der Worker verarbeitet das
    # gesamte Audio deterministisch im Drain-Teil (read_new -> feed -> flush)
    streaming.start()
    streaming.stop_and_flush(timeout=10.0)
    return partials, finals, errors


def test_finals_accumulate_in_order(tmp_path):
    audio = np.concatenate([
        _tone(1.0), _silence(1.0),   # Segment 1 (durch Stille finalisiert)
        _tone(0.6),                  # Segment 2 (durch flush finalisiert)
    ])
    partials, finals, errors = _run_streaming(audio, tmp_path)
    assert errors == []
    assert len(finals) == 2
    assert all(isinstance(f, str) and f.strip() for f in finals)


def test_preview_never_cleared_with_empty_text(tmp_path):
    """Regression: Beim Finalisieren wurde die Vorschau mit '' geleert -
    der angezeigte Text 'verschwand' waehrend der Finalisierung."""
    audio = np.concatenate([_tone(1.0), _silence(1.0), _tone(0.8), _silence(1.0)])
    partials, finals, _ = _run_streaming(audio, tmp_path)
    assert len(finals) == 2
    # on_partial darf nie mit leerem Text aufgerufen werden
    assert all(p.strip() for p in partials)


def test_streaming_collects_finals_attribute(tmp_path):
    audio = np.concatenate([_tone(1.0), _silence(1.0)])
    config = Config(config_file=tmp_path / "config.json")
    streaming = StreamingTranscriber(
        FakeRecorder(audio), FakeService(), config,
        on_partial=lambda t: None, on_final=lambda t: None,
        on_error=lambda m, h: None)
    streaming.start()
    streaming.stop_and_flush(timeout=10.0)
    assert streaming.finals  # fuer den End-Inject-Modus gesammelt


def test_transcription_error_reported_not_silent(tmp_path):
    class BrokenService:
        def transcribe(self, audio, is_stream_segment=False, apply_dictionary=True):
            raise RuntimeError("kaputt")

    config = Config(config_file=tmp_path / "config.json")
    errors = []
    streaming = StreamingTranscriber(
        FakeRecorder(np.concatenate([_tone(1.0), _silence(1.0)])),
        BrokenService(), config,
        on_partial=lambda t: None, on_final=lambda t: None,
        on_error=lambda m, h: errors.append((m, h)))
    streaming.start()
    streaming.stop_and_flush(timeout=10.0)
    assert errors, "Fehler muss gemeldet werden (kein stilles Scheitern)"
    message, hint = errors[0]
    assert "fehlgeschlagen" in message
    assert hint  # Loesungshinweis vorhanden
