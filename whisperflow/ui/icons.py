# -*- coding: utf-8 -*-
"""Programmatisch gezeichnete Status-Icons.

Jeder Zustand bekommt eine eigene Farbe UND Form (farbfehlsichtig-tauglich):
  Bereit       gruener Kreis mit Mikrofon
  Aufnahme     roter Kreis mit Aufnahme-Punkt
  Verarbeitung oranger Kreis mit Sanduhr-Balken
  Fehler       gelbes Warndreieck mit Ausrufezeichen
  Pausiert     grauer Kreis mit Pause-Balken
  Laden        blauer Kreis mit Punkten
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from whisperflow.state import AppState

COLORS = {
    AppState.READY: "#2e9e5b",
    AppState.RECORDING: "#d93025",
    AppState.PROCESSING: "#e8842c",
    AppState.ERROR: "#f0b429",
    AppState.PAUSED: "#8a8a8a",
    AppState.LOADING: "#3f7fd4",
}

_SIZE = 64
_cache = {}


def _painter(pixmap):
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    return p


def _draw_mic(p, color):
    """Weisses Mikrofon auf farbigem Kreis."""
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)
    p.setBrush(QBrush(QColor("white")))
    # Mikrofon-Korpus
    p.drawRoundedRect(QRectF(26, 14, 12, 22), 6, 6)
    # Buegel
    pen = QPen(QColor("white"), 4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(20, 22, 24, 22), 180 * 16, 180 * 16)
    p.drawLine(32, 44, 32, 50)
    p.drawLine(24, 50, 40, 50)


def _draw_record(p, color):
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)
    p.setBrush(QBrush(QColor("white")))
    p.drawEllipse(20, 20, 24, 24)


def _draw_processing(p, color):
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)
    # Sanduhr-Silhouette
    p.setBrush(QBrush(QColor("white")))
    top = QPolygonF([QPointF(22, 16), QPointF(42, 16), QPointF(32, 32)])
    bottom = QPolygonF([QPointF(32, 32), QPointF(22, 48), QPointF(42, 48)])
    p.drawPolygon(top)
    p.drawPolygon(bottom)


def _draw_error(p, color):
    # Warndreieck statt Kreis - eigene Form fuer den Fehlerzustand
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    triangle = QPolygonF([QPointF(32, 4), QPointF(61, 56), QPointF(3, 56)])
    p.drawPolygon(triangle)
    p.setBrush(QBrush(QColor("#202020")))
    p.drawRoundedRect(QRectF(28, 20, 8, 20), 3, 3)
    p.drawEllipse(28, 44, 8, 8)


def _draw_paused(p, color):
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)
    p.setBrush(QBrush(QColor("white")))
    p.drawRoundedRect(QRectF(22, 18, 7, 28), 2, 2)
    p.drawRoundedRect(QRectF(35, 18, 7, 28), 2, 2)


def _draw_loading(p, color):
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)
    p.setBrush(QBrush(QColor("white")))
    for i, x in enumerate((16, 28, 40)):
        size = 8 if i == 1 else 7
        p.drawEllipse(x, 30 - size // 2, size, size)


_DRAWERS = {
    AppState.READY: _draw_mic,
    AppState.RECORDING: _draw_record,
    AppState.PROCESSING: _draw_processing,
    AppState.ERROR: _draw_error,
    AppState.PAUSED: _draw_paused,
    AppState.LOADING: _draw_loading,
}


def state_icon(state: AppState) -> QIcon:
    """Icon fuer einen Zustand (gecacht)."""
    if state in _cache:
        return _cache[state]
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.transparent)
    p = _painter(pixmap)
    try:
        _DRAWERS[state](p, COLORS[state])
    finally:
        p.end()
    icon = QIcon(pixmap)
    _cache[state] = icon
    return icon


def app_icon() -> QIcon:
    return state_icon(AppState.READY)
