# -*- coding: utf-8 -*-
"""Tests fuer die Zustandsmaschine (Status-Feedback)."""

from whisperflow.state import AppState, StateMachine


def test_initial_state_is_loading():
    sm = StateMachine()
    assert sm.state == AppState.LOADING


def test_normal_dictation_cycle():
    sm = StateMachine()
    assert sm.transition(AppState.READY)
    assert sm.transition(AppState.RECORDING)
    assert sm.transition(AppState.PROCESSING)
    assert sm.transition(AppState.READY)


def test_recording_blocked_while_processing():
    sm = StateMachine()
    sm.transition(AppState.READY)
    sm.transition(AppState.RECORDING)
    sm.transition(AppState.PROCESSING)
    # Kein neuer Aufnahme-Start waehrend der Verarbeitung
    assert not sm.transition(AppState.RECORDING)
    assert sm.state == AppState.PROCESSING


def test_recording_blocked_while_paused():
    sm = StateMachine()
    sm.transition(AppState.READY)
    sm.transition(AppState.PAUSED)
    assert not sm.transition(AppState.RECORDING)


def test_error_reachable_from_any_state_and_carries_hint():
    sm = StateMachine()
    sm.transition(AppState.READY)
    sm.transition(AppState.RECORDING)
    assert sm.error("Mikrofon weg", hint="Geraet pruefen")
    assert sm.state == AppState.ERROR
    assert sm.info.message == "Mikrofon weg"
    assert sm.info.hint == "Geraet pruefen"


def test_retry_after_error():
    sm = StateMachine()
    sm.error("kaputt")
    # Aus dem Fehlerzustand darf direkt wieder aufgenommen werden
    assert sm.transition(AppState.RECORDING)


def test_listeners_notified():
    sm = StateMachine()
    seen = []
    sm.add_listener(lambda info: seen.append(info.state))
    sm.transition(AppState.READY)
    sm.transition(AppState.RECORDING)
    assert seen == [AppState.READY, AppState.RECORDING]


def test_failing_listener_does_not_break_transitions():
    sm = StateMachine()

    def bad_listener(info):
        raise RuntimeError("boom")

    sm.add_listener(bad_listener)
    assert sm.transition(AppState.READY)
    assert sm.state == AppState.READY
