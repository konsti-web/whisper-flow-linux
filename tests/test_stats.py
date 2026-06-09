# -*- coding: utf-8 -*-
"""Tests fuer die Zeitersparnis-Statistik."""

import pytest

from whisperflow.stats import StatsTracker, count_words, saved_seconds


def _tracker(tmp_path, wpm=40):
    return StatsTracker(path=tmp_path / "stats.json", typing_wpm=wpm)


# --- Berechnung ---------------------------------------------------------------

def test_saved_seconds_basic():
    # 100 Woerter: tippen @40 WPM = 150 s; gesprochen in 60 s -> 90 s gespart
    assert saved_seconds(100, 60.0, 40) == pytest.approx(90.0)


def test_saved_seconds_never_negative():
    # 10 Woerter in 2 Minuten gesprochen - Tippen waere schneller gewesen
    assert saved_seconds(10, 120.0, 40) == 0.0


def test_saved_seconds_edge_cases():
    assert saved_seconds(0, 10.0, 40) == 0.0
    assert saved_seconds(-5, 10.0, 40) == 0.0
    assert saved_seconds(100, 60.0, 0) == 0.0


def test_configurable_wpm():
    # Schnellere Tipper sparen weniger
    assert saved_seconds(100, 60.0, 80) == pytest.approx(15.0)
    assert saved_seconds(100, 60.0, 40) > saved_seconds(100, 60.0, 80)


def test_count_words():
    assert count_words("Hallo schoene Welt") == 3
    assert count_words("") == 0
    assert count_words("   ") == 0


# --- Erfassung & Kumulierung -----------------------------------------------------

def test_record_accumulates(tmp_path):
    t = _tracker(tmp_path)
    t.record(100, 60.0)   # +90 s
    t.record(50, 30.0)    # tippen 75 s -> +45 s
    s = t.summary()
    assert s["total_words"] == 150
    assert s["total_dictations"] == 2
    assert s["total_saved_minutes"] == pytest.approx((90 + 45) / 60.0)
    assert s["total_speech_minutes"] == pytest.approx(1.5)


def test_record_ignores_empty_dictation(tmp_path):
    t = _tracker(tmp_path)
    assert t.record(0, 10.0) == 0.0
    assert t.summary()["total_dictations"] == 0


def test_spoken_wpm(tmp_path):
    t = _tracker(tmp_path)
    t.record(120, 60.0)
    assert t.summary()["avg_spoken_wpm"] == pytest.approx(120.0)


def test_persistence_roundtrip(tmp_path):
    t = _tracker(tmp_path)
    t.record(100, 60.0, processing_seconds=2.0)

    t2 = _tracker(tmp_path)
    s = t2.summary()
    assert s["total_words"] == 100
    assert s["total_saved_minutes"] == pytest.approx(1.5)
    assert len(t2.recent) == 1


def test_reset(tmp_path):
    t = _tracker(tmp_path)
    t.record(100, 60.0)
    t.reset()
    s = t.summary()
    assert s["total_words"] == 0
    assert s["total_saved_minutes"] == 0.0

    t2 = _tracker(tmp_path)
    assert t2.summary()["total_words"] == 0


def test_recent_limit(tmp_path):
    t = _tracker(tmp_path)
    for _ in range(60):
        t.record(10, 1.0)
    assert len(t.recent) == StatsTracker.RECENT_LIMIT


def test_tray_label_format(tmp_path):
    t = _tracker(tmp_path)
    t.record(100, 60.0)
    label = t.tray_label()
    assert "Min gespart" in label
    assert "100" in label
