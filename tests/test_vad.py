# -*- coding: utf-8 -*-
"""Tests fuer die Energie-VAD-Segmentierung (Live-Transkription)."""

import numpy as np

from whisperflow.audio.vad import FRAME_MS, SegmenterConfig, StreamSegmenter

RATE = 16000


def _silence(seconds):
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def _speech(seconds, amplitude=0.1):
    t = np.linspace(0, seconds, int(RATE * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _segmenter(**kwargs):
    cfg = SegmenterConfig(adaptive=False, **kwargs)
    return StreamSegmenter(cfg)


def _feed_chunked(seg, audio, chunk_s=0.1):
    """Fuettert Audio in Echtzeit-aehnlichen Stuecken, sammelt Segmente."""
    finished = []
    chunk = int(RATE * chunk_s)
    for i in range(0, len(audio), chunk):
        finished.extend(seg.feed(audio[i:i + chunk]))
    return finished


def test_single_utterance_finalized_after_silence():
    seg = _segmenter()
    audio = np.concatenate([_silence(0.4), _speech(1.0), _silence(1.0)])
    finished = _feed_chunked(seg, audio)
    assert len(finished) == 1
    # Segment enthaelt die Sprache (ca. 1 s) plus etwas Kontext
    assert 0.8 * RATE <= len(finished[0]) <= 1.8 * RATE


def test_two_utterances_give_two_segments():
    seg = _segmenter()
    audio = np.concatenate([
        _speech(0.8), _silence(1.0),
        _speech(0.6), _silence(1.0),
    ])
    finished = _feed_chunked(seg, audio)
    assert len(finished) == 2


def test_short_blip_is_discarded():
    seg = _segmenter(min_speech_ms=250)
    audio = np.concatenate([_silence(0.3), _speech(0.06), _silence(1.0)])
    finished = _feed_chunked(seg, audio)
    assert finished == []


def test_max_segment_forces_split():
    seg = _segmenter(max_segment_s=2.0)
    finished = _feed_chunked(seg, _speech(7.0))
    tail = seg.flush()
    if tail is not None:
        finished.append(tail)
    # 7 s Dauersprache mit 2-s-Limit -> mindestens 3 Segmente
    assert len(finished) >= 3
    for s in finished[:-1]:
        assert len(s) <= 2.2 * RATE


def test_current_returns_open_segment_during_speech():
    seg = _segmenter()
    seg.feed(_speech(0.5))
    current = seg.current()
    assert current is not None
    assert len(current) >= 0.3 * RATE


def test_current_none_during_silence():
    seg = _segmenter()
    seg.feed(_silence(0.5))
    assert seg.current() is None


def test_flush_returns_tail():
    seg = _segmenter()
    seg.feed(_speech(0.7))  # keine Stille danach -> noch offen
    tail = seg.flush()
    assert tail is not None
    assert len(tail) >= 0.5 * RATE
    # Nach flush ist nichts mehr offen
    assert seg.current() is None


def test_flush_empty_when_nothing_recorded():
    seg = _segmenter()
    seg.feed(_silence(0.5))
    assert seg.flush() is None


def test_preroll_included_at_speech_start():
    seg = _segmenter()
    audio = np.concatenate([_silence(1.0), _speech(1.0), _silence(1.0)])
    finished = _feed_chunked(seg, audio)
    assert len(finished) == 1
    # Pre-Roll: Segment beginnt vor dem eigentlichen Sprachbeginn
    assert len(finished[0]) > 1.0 * RATE


def test_adaptive_threshold_ignores_noise_floor():
    cfg = SegmenterConfig(adaptive=True, threshold=0.006)
    seg = StreamSegmenter(cfg)
    rng = np.random.default_rng(42)
    noise = (0.004 * rng.standard_normal(int(RATE * 2.0))).astype(np.float32)
    finished = _feed_chunked(seg, noise)
    # Konstantes Grundrauschen knapp unter/um die Schwelle startet kein Segment
    assert finished == []
    assert seg.current() is None


def test_frame_ms_constant_sane():
    assert 10 <= FRAME_MS <= 50
