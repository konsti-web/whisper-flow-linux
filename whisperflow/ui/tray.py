# -*- coding: utf-8 -*-
"""System-Tray-Icon mit Statusanzeige und Menue (QSystemTrayIcon).

Hinweis GNOME: Wie zuvor bei AppIndicator3 wird die Erweiterung
"AppIndicator and KStatusNotifierItem Support" benoetigt.
"""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from whisperflow.state import AppState, StateInfo
from whisperflow.ui.icons import state_icon


class TrayUI:
    def __init__(self, app):
        """app: WhisperFlowApp (Orchestrierung)."""
        self.app = app
        self.tray = QSystemTrayIcon(state_icon(AppState.LOADING))
        self.tray.setToolTip("Whisper Flow")

        self.menu = QMenu()

        self.status_action = QAction("Lade Modell...")
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        self.stats_action = QAction("")
        self.stats_action.setEnabled(False)
        self.menu.addAction(self.stats_action)

        self.menu.addSeparator()

        self.pause_action = QAction("Pausieren")
        self.pause_action.triggered.connect(self.app.toggle_pause)
        self.menu.addAction(self.pause_action)

        self.mode_action = QAction("")
        self.mode_action.triggered.connect(self.app.toggle_mode)
        self.menu.addAction(self.mode_action)

        self.menu.addSeparator()

        history_action = QAction("Verlauf && Korrekturen...")
        history_action.triggered.connect(self.app.show_history)
        self.menu.addAction(history_action)
        self._history_action = history_action

        settings_action = QAction("Einstellungen...")
        settings_action.triggered.connect(self.app.show_settings)
        self.menu.addAction(settings_action)
        self._settings_action = settings_action

        self.menu.addSeparator()

        quit_action = QAction("Beenden")
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)
        self._quit_action = quit_action

        self.tray.setContextMenu(self.menu)
        self.refresh_mode_label()
        self.refresh_stats_label()
        self.tray.show()

    # -- Slots (laufen im GUI-Thread) ----------------------------------------

    def update_state(self, info: StateInfo):
        self.tray.setIcon(state_icon(info.state))
        text = info.label
        if info.state == AppState.ERROR and info.message:
            text = "Fehler: {}".format(info.message)
        self.status_action.setText(text[:80])
        tooltip = "Whisper Flow - {}".format(text)
        if info.hint:
            tooltip += "\n{}".format(info.hint)
        self.tray.setToolTip(tooltip)

    def refresh_mode_label(self):
        mode = self.app.config.get("mode")
        label = "Modus: Live-Transkription" if mode == "live" else "Modus: Batch (am Ende)"
        self.mode_action.setText(label + "  (wechseln)")

    def refresh_stats_label(self):
        if self.app.config.get("stats_enabled"):
            self.stats_action.setText(self.app.stats.tray_label())
            self.stats_action.setVisible(True)
        else:
            self.stats_action.setVisible(False)

    def update_pause_label(self, paused: bool):
        self.pause_action.setText("Fortsetzen" if paused else "Pausieren")

    def notify(self, title: str, message: str, error: bool = False):
        icon = QSystemTrayIcon.MessageIcon.Critical if error \
            else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage("Whisper Flow - {}".format(title), message, icon, 4000)

    def hide(self):
        self.tray.hide()
