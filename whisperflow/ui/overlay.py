# -*- coding: utf-8 -*-
"""Aufnahme-Overlay: VU-Meter plus Live-Text (vorlaeufig/final).

Portierung des Cairo-VU-Meters auf QPainter, erweitert um eine
Textzeile fuer die Live-Transkription. Das Fenster ist klick-durchlaessig
und nimmt keinen Fokus an.

Hinweis Wayland: Compositors erlauben Apps keine freie Positionierung;
dort bestimmt der Compositor, wo das Overlay erscheint.
"""

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from whisperflow.state import AppState

NUM_BARS = 7
BAR_WIDTH = 8
BAR_GAP = 5
BAR_MAX_HEIGHT = 44
BAR_MIN_HEIGHT = 6
PADDING = 14
TEXT_WIDTH = 380
TEXT_LINES = 3

STATE_BORDER = {
    AppState.RECORDING: "#d93025",
    AppState.PROCESSING: "#e8842c",
    AppState.ERROR: "#f0b429",
}


class RecordingOverlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._level = 0.0
        self._bar_heights = [0.0] * NUM_BARS
        self._final_text = ""
        self._partial_text = ""
        self._show_text = True
        self._state = AppState.RECORDING

        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20 fps
        self._timer.timeout.connect(self._tick)

        self._apply_size()

    # -- Layout ---------------------------------------------------------------

    def _apply_size(self):
        bars_width = NUM_BARS * BAR_WIDTH + (NUM_BARS - 1) * BAR_GAP
        width = PADDING * 2 + bars_width
        if self._show_text:
            width += PADDING + TEXT_WIDTH
        height = PADDING * 2 + max(BAR_MAX_HEIGHT, 16 * TEXT_LINES + 14)
        self.setFixedSize(width, height)
        self._move_bottom_center()

    def _move_bottom_center(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + geo.height() - self.height() - 60
        self.move(x, y)

    # -- API (im GUI-Thread aufrufen) -------------------------------------------

    def show_recording(self, show_text: bool):
        self._final_text = ""
        self._partial_text = ""
        self._show_text = show_text
        self._state = AppState.RECORDING
        self._bar_heights = [0.0] * NUM_BARS
        self._level = 0.0
        self._apply_size()
        self.show()
        self._timer.start()

    def show_processing(self):
        self._state = AppState.PROCESSING
        self._level = 0.0
        self.update()

    def hide_overlay(self):
        self._timer.stop()
        self.hide()
        self._level = 0.0
        self._bar_heights = [0.0] * NUM_BARS
        self._final_text = ""
        self._partial_text = ""

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, float(level)))

    def set_live_text(self, final_tail: str, partial: str):
        self._final_text = final_tail or ""
        self._partial_text = partial or ""
        self.update()

    # -- Animation/Zeichnung ----------------------------------------------------

    def _tick(self):
        level = self._level if self._state == AppState.RECORDING else 0.0
        center = (NUM_BARS - 1) / 2.0
        for i in range(NUM_BARS):
            dist = abs(i - center) / center
            weight = 1.0 - 0.5 * dist * dist
            target = level * weight
            if target > self._bar_heights[i]:
                self._bar_heights[i] += (target - self._bar_heights[i]) * 0.5
            else:
                self._bar_heights[i] += (target - self._bar_heights[i]) * 0.15
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Panel mit zustandsabhaengigem Rand (Statusanzeige Punkt 6)
        panel = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setBrush(QColor(20, 20, 24, 235))
        border = QColor(STATE_BORDER.get(self._state, "#555555"))
        p.setPen(border)
        p.drawRoundedRect(panel, 12, 12)

        # VU-Balken
        base_y = self.height() - PADDING
        for i in range(NUM_BARS):
            h = BAR_MIN_HEIGHT + self._bar_heights[i] * (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT)
            x = PADDING + i * (BAR_WIDTH + BAR_GAP)
            y = base_y - h
            frac = self._bar_heights[i]
            if frac < 0.5:
                color = QColor.fromRgbF(frac * 2, 0.8, 0.1, 0.95)
            else:
                color = QColor.fromRgbF(1.0, max(0.0, 0.8 * (1.0 - (frac - 0.5) * 2)), 0.1, 0.95)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y, BAR_WIDTH, h), BAR_WIDTH / 2.0, BAR_WIDTH / 2.0)

        # Status-Caption ueber den Balken
        p.setPen(border)
        font = QFont()
        font.setPointSize(8)
        p.setFont(font)
        caption = {"recording": "● Aufnahme", "processing": "⏳ Verarbeite…"}.get(
            self._state.value, "")
        bars_width = NUM_BARS * BAR_WIDTH + (NUM_BARS - 1) * BAR_GAP
        p.drawText(QRectF(PADDING - 6, 2, bars_width + 12, 14), Qt.AlignCenter, caption)

        # Live-Text rechts neben den Balken
        if self._show_text:
            text_x = PADDING * 2 + bars_width
            text_rect = QRectF(text_x, PADDING - 4, TEXT_WIDTH, self.height() - PADDING * 2 + 8)
            font.setPointSize(10)
            p.setFont(font)

            display_final = self._final_text
            display_partial = self._partial_text
            if not display_final and not display_partial:
                p.setPen(QColor(150, 150, 150))
                p.drawText(text_rect, Qt.AlignVCenter | Qt.TextWordWrap, "Sprich jetzt…")
            else:
                # Finaler Text weiss, vorlaeufiger Text grau-kursiv dahinter
                combined = display_final
                if display_partial:
                    combined = (combined + " " if combined else "") + display_partial
                # Nur das Ende anzeigen, das in die Box passt
                metrics = p.fontMetrics()
                max_chars = max(20, int(TEXT_WIDTH / max(1, metrics.averageCharWidth())) * TEXT_LINES)
                if len(combined) > max_chars:
                    combined = "…" + combined[-max_chars:]
                    if display_partial and len(display_partial) < len(combined):
                        display_partial = display_partial[-max_chars:]
                if display_partial and combined.endswith(display_partial):
                    final_part = combined[: len(combined) - len(display_partial)]
                else:
                    final_part, display_partial = combined, ""

                # Zwei Farben: zuerst final, dann partial - vereinfacht als
                # ein Block gezeichnet, partial in grau wenn allein
                if final_part.strip():
                    p.setPen(QColor(240, 240, 240))
                    p.drawText(text_rect, Qt.AlignVCenter | Qt.TextWordWrap,
                               final_part + (" " + display_partial if display_partial else ""))
                else:
                    italic = QFont(font)
                    italic.setItalic(True)
                    p.setFont(italic)
                    p.setPen(QColor(170, 170, 170))
                    p.drawText(text_rect, Qt.AlignVCenter | Qt.TextWordWrap, display_partial)
