# -*- coding: utf-8 -*-
"""Verlaufsfenster: letzte Diktate ansehen und korrigieren.

Korrekturen hier sind die Lernquelle des Woerterbuchs: Beim Speichern
wird der Wort-Diff an UserDictionary.observe_correction() uebergeben.
"""

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout,
)


class CorrectionDialog(QDialog):
    def __init__(self, original: str, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diktat korrigieren")
        self.resize(520, 260)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Original (transkribiert):"))
        original_view = QPlainTextEdit(original)
        original_view.setReadOnly(True)
        original_view.setMaximumHeight(70)
        layout.addWidget(original_view)

        layout.addWidget(QLabel("Korrigierte Fassung:"))
        self.editor = QPlainTextEdit(current or original)
        layout.addWidget(self.editor)

        hint = QLabel("Gleiche Korrektur mehrfach gespeichert → wird automatisch "
                      "ins Wörterbuch übernommen.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def corrected_text(self) -> str:
        return self.editor.toPlainText().strip()


class HistoryWindow(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("Whisper Flow - Verlauf")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        info = QLabel("Doppelklick auf ein Diktat, um es zu korrigieren. "
                      "Wiederholte Korrekturen lernt das Wörterbuch automatisch.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.listing = QListWidget()
        self.listing.itemDoubleClicked.connect(self._on_edit)
        layout.addWidget(self.listing)

        button_row = QHBoxLayout()
        edit_btn = QPushButton("Korrigieren...")
        edit_btn.clicked.connect(lambda: self._on_edit(self.listing.currentItem()))
        button_row.addWidget(edit_btn)

        copy_btn = QPushButton("Erneut einfügen")
        copy_btn.setToolTip("Fügt den Text noch einmal an der Cursor-Position ein")
        copy_btn.clicked.connect(self._on_reinject)
        button_row.addWidget(copy_btn)

        clear_btn = QPushButton("Verlauf leeren")
        clear_btn.clicked.connect(self._on_clear)
        button_row.addWidget(clear_btn)

        button_row.addStretch()
        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        self.refresh()

    def refresh(self):
        self.listing.clear()
        entries = self.app.history.list_entries()
        for index, entry in enumerate(entries):
            shown = entry.get("corrected") or entry.get("text") or ""
            stamp = time.strftime("%d.%m. %H:%M", time.localtime(entry.get("ts", 0)))
            preview = shown if len(shown) <= 90 else shown[:87] + "…"
            suffix = "  ✎" if entry.get("corrected") else ""
            item = QListWidgetItem("[{}] {}{}".format(stamp, preview, suffix))
            item.setData(Qt.UserRole, index)
            self.listing.addItem(item)
        self.listing.scrollToBottom()

    def _selected_index(self):
        item = self.listing.currentItem()
        return None if item is None else item.data(Qt.UserRole)

    def _on_edit(self, item):
        if item is None:
            return
        index = item.data(Qt.UserRole)
        entries = self.app.history.list_entries()
        if index is None or index >= len(entries):
            return
        entry = entries[index]
        original = entry.get("text") or ""
        dialog = CorrectionDialog(original, entry.get("corrected") or "", self)
        if dialog.exec() != QDialog.Accepted:
            return
        corrected = dialog.corrected_text()
        if not corrected or corrected == (entry.get("corrected") or original):
            return
        self.app.history.set_corrected(index, corrected)
        learned = self.app.on_user_correction(original, corrected)
        self.refresh()
        if learned:
            names = ", ".join("'{}' → '{}'".format(c.wrong, c.right) for c in learned)
            self.app.notify("Wörterbuch", "Gelernt: {}".format(names))

    def _on_reinject(self):
        index = self._selected_index()
        if index is None:
            return
        entries = self.app.history.list_entries()
        if index >= len(entries):
            return
        entry = entries[index]
        text = entry.get("corrected") or entry.get("text") or ""
        if text:
            self.app.reinject_text(text)

    def _on_clear(self):
        self.app.history.clear()
        self.refresh()
