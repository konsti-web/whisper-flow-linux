# -*- coding: utf-8 -*-
"""Einstellungsdialog (Tabs): Allgemein, Audio, Steuerung, Whisper,
Woerterbuch, Statistik, System.

Alle Funktionen sind konfigurierbar; "Auto" laesst die App die beste
Konfiguration selbst waehlen (Hardware-Erkennung).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from whisperflow import autostart
from whisperflow.audio.devices import get_default_input_name, get_input_devices
from whisperflow.hotkeys.base import display_name

MODELS = ["auto", "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
BACKENDS = [("auto", "Auto (empfohlen)"),
            ("faster-whisper", "faster-whisper (NVIDIA/CPU)"),
            ("whisper-cpp", "whisper.cpp (Metal/Vulkan)"),
            ("openai-whisper", "openai-whisper (AMD ROCm)")]
DEVICES = [("auto", "Auto (empfohlen)"), ("cpu", "CPU"), ("cuda", "CUDA (NVIDIA)"),
           ("metal", "Metal (macOS)"), ("vulkan", "Vulkan (AMD/Intel)")]
COMPUTE = ["auto", "float16", "int8", "float32", "int8_float16", "int8_float32"]
LANGUAGES = [("auto", "Automatisch"), ("de", "Deutsch"), ("en", "Englisch"),
             ("fr", "Französisch"), ("es", "Spanisch"), ("it", "Italienisch"),
             ("pt", "Portugiesisch"), ("nl", "Niederländisch"), ("pl", "Polnisch"),
             ("ru", "Russisch"), ("ja", "Japanisch"), ("zh", "Chinesisch")]


class CaptureDialog(QDialog):
    """Erfasst eine Taste/Maustaste ueber das Hotkey-Backend."""

    captured = Signal(object)

    def __init__(self, hotkey_backend, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trigger erfassen")
        self.setModal(True)
        self.resize(360, 120)
        self.result_trigger = None

        layout = QVBoxLayout(self)
        label = QLabel("Drücke eine Taste oder Maus-Seitentaste...\n"
                       "(Esc bricht ab; Maus links/rechts/Mitte werden ignoriert)")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.captured.connect(self._on_captured)
        hotkey_backend.capture_once(self.captured.emit, timeout=6.0)
        QTimer.singleShot(6500, self._timeout_close)

    def _on_captured(self, serialized):
        self.result_trigger = serialized
        self.accept() if serialized else self.reject()

    def _timeout_close(self):
        if self.result_trigger is None and self.isVisible():
            self.reject()


class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.config = app.config
        self.setWindowTitle("Whisper Flow - Einstellungen")
        self.resize(640, 520)

        self._trigger_list = list(self.config.get("trigger_keys") or [])

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_general_tab(), "Allgemein")
        self.tabs.addTab(self._build_audio_tab(), "Audio")
        self.tabs.addTab(self._build_control_tab(), "Steuerung")
        self.tabs.addTab(self._build_whisper_tab(), "Whisper")
        self.tabs.addTab(self._build_dictionary_tab(), "Wörterbuch")
        self.tabs.addTab(self._build_stats_tab(), "Statistik")
        self.tabs.addTab(self._build_system_tab(), "System")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- Tab: Allgemein ---------------------------------------------------------

    def _build_general_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Live-Transkription (während des Sprechens)", "live")
        self.mode_combo.addItem("Batch (nach Aufnahme-Ende, wie bisher)", "batch")
        self.mode_combo.setCurrentIndex(0 if self.config.get("mode") == "live" else 1)
        form.addRow("Transkription:", self.mode_combo)

        self.inject_combo = QComboBox()
        self.inject_combo.addItem("Segmentweise einfügen (sofort)", "segment")
        self.inject_combo.addItem("Erst am Ende einfügen", "end")
        self.inject_combo.setCurrentIndex(
            0 if self.config.get("live_inject") == "segment" else 1)
        form.addRow("Live-Einfügen:", self.inject_combo)

        self.lang_combo = QComboBox()
        current_lang = self.config.get("language") or "auto"
        for code, label in LANGUAGES:
            self.lang_combo.addItem(label, code)
            if code == current_lang:
                self.lang_combo.setCurrentIndex(self.lang_combo.count() - 1)
        form.addRow("Sprache:", self.lang_combo)

        self.overlay_check = QCheckBox("Overlay während der Aufnahme anzeigen")
        self.overlay_check.setChecked(bool(self.config.get("show_overlay")))
        form.addRow("", self.overlay_check)

        return tab

    # -- Tab: Audio ----------------------------------------------------------------

    def _build_audio_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.device_combo = QComboBox()
        default_name = get_default_input_name()
        label = "System-Standard" + (" ({})".format(default_name[:38]) if default_name else "")
        self.device_combo.addItem(label, None)
        current = self.config.get("input_device")
        for dev in get_input_devices():
            name = dev["name"]
            shown = name if len(name) <= 48 else name[:45] + "…"
            self.device_combo.addItem(shown, name)
            if current and name == current:
                self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        form.addRow("Aufnahmegerät:", self.device_combo)
        return tab

    # -- Tab: Steuerung ----------------------------------------------------------------

    def _build_control_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Trigger-Tasten (gedrückt halten zum Diktieren)")
        group_layout = QVBoxLayout(group)
        self.trigger_listing = QListWidget()
        self.trigger_listing.setMaximumHeight(110)
        self._refresh_triggers()
        group_layout.addWidget(self.trigger_listing)

        row = QHBoxLayout()
        capture_btn = QPushButton("Erfassen...")
        capture_btn.clicked.connect(self._on_capture)
        row.addWidget(capture_btn)
        remove_btn = QPushButton("Entfernen")
        remove_btn.clicked.connect(self._on_remove_trigger)
        row.addWidget(remove_btn)
        row.addStretch()
        group_layout.addLayout(row)
        layout.addWidget(group)

        form = QFormLayout()
        self.hold_spin = QDoubleSpinBox()
        self.hold_spin.setRange(0.1, 2.0)
        self.hold_spin.setSingleStep(0.1)
        self.hold_spin.setDecimals(1)
        self.hold_spin.setSuffix(" s")
        self.hold_spin.setValue(float(self.config.get("hold_threshold")))
        form.addRow("Haltezeit bis Aufnahme:", self.hold_spin)

        self.double_tap_check = QCheckBox("Doppel-Tipp für freihändiges Diktieren")
        self.double_tap_check.setChecked(bool(self.config.get("double_tap_enabled")))
        form.addRow("", self.double_tap_check)
        layout.addLayout(form)
        layout.addStretch()
        return tab

    def _refresh_triggers(self):
        self.trigger_listing.clear()
        for trigger in self._trigger_list:
            item = QListWidgetItem(display_name(trigger))
            item.setData(Qt.UserRole, trigger)
            self.trigger_listing.addItem(item)

    def _on_capture(self):
        if self.app.hotkey_backend is None:
            QMessageBox.warning(self, "Nicht verfügbar",
                                "Kein Hotkey-Backend aktiv.\n" + (self.app.hotkey_warning or ""))
            return
        dialog = CaptureDialog(self.app.hotkey_backend, self)
        if dialog.exec() == QDialog.Accepted and dialog.result_trigger:
            if dialog.result_trigger not in self._trigger_list:
                self._trigger_list.append(dialog.result_trigger)
                self._refresh_triggers()

    def _on_remove_trigger(self):
        item = self.trigger_listing.currentItem()
        if item is None:
            return
        trigger = item.data(Qt.UserRole)
        if trigger in self._trigger_list:
            self._trigger_list.remove(trigger)
        self._refresh_triggers()

    # -- Tab: Whisper -------------------------------------------------------------------

    def _build_whisper_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hw_group = QGroupBox("Erkannte Hardware")
        hw_layout = QVBoxLayout(hw_group)
        self.hw_label = QLabel("...")
        self.hw_label.setWordWrap(True)
        hw_layout.addWidget(self.hw_label)
        self.rec_label = QLabel("")
        self.rec_label.setWordWrap(True)
        self.rec_label.setStyleSheet("color: gray;")
        hw_layout.addWidget(self.rec_label)
        layout.addWidget(hw_group)
        self._fill_hardware_info()

        form = QFormLayout()
        self.backend_combo = QComboBox()
        for code, label in BACKENDS:
            self.backend_combo.addItem(label, code)
        self._set_combo(self.backend_combo, self.config.get("backend"))
        form.addRow("Backend:", self.backend_combo)

        self.model_combo = QComboBox()
        for m in MODELS:
            self.model_combo.addItem("Auto (empfohlen)" if m == "auto" else m, m)
        self._set_combo(self.model_combo, self.config.get("model_size"))
        form.addRow("Modell:", self.model_combo)

        self.device_hw_combo = QComboBox()
        for code, label in DEVICES:
            self.device_hw_combo.addItem(label, code)
        self._set_combo(self.device_hw_combo, self.config.get("device"))
        form.addRow("Gerät:", self.device_hw_combo)

        self.compute_combo = QComboBox()
        for c in COMPUTE:
            self.compute_combo.addItem("Auto (empfohlen)" if c == "auto" else c, c)
        self._set_combo(self.compute_combo, self.config.get("compute_type"))
        form.addRow("Rechentyp:", self.compute_combo)
        layout.addLayout(form)

        live_group = QGroupBox("Live-Transkription (Feintuning)")
        live_form = QFormLayout(live_group)
        self.preview_spin = QDoubleSpinBox()
        self.preview_spin.setRange(0.3, 5.0)
        self.preview_spin.setSingleStep(0.1)
        self.preview_spin.setSuffix(" s")
        self.preview_spin.setValue(float(self.config.get("live_preview_interval")))
        live_form.addRow("Vorschau-Intervall:", self.preview_spin)

        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(200, 3000)
        self.silence_spin.setSingleStep(50)
        self.silence_spin.setSuffix(" ms")
        self.silence_spin.setValue(int(self.config.get("vad_silence_ms")))
        live_form.addRow("Pause bis Segment-Ende:", self.silence_spin)
        layout.addWidget(live_group)

        note = QLabel("Backend-/Modell-Änderungen laden das Modell neu (ohne Neustart).")
        note.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note)
        layout.addStretch()
        return tab

    def _fill_hardware_info(self):
        try:
            from whisperflow.hardware import available_backends, detect_hardware, recommend
            hw = detect_hardware()
            rec = recommend(hw, available_backends())
            self.hw_label.setText(hw.describe())
            self.rec_label.setText("Empfehlung: {} · {} · {} · Modell {}\n{}".format(
                rec.backend, rec.device, rec.compute_type, rec.model_size, rec.reason))
        except Exception as e:
            self.hw_label.setText("Erkennung fehlgeschlagen: {}".format(e))

    @staticmethod
    def _set_combo(combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # -- Tab: Woerterbuch -------------------------------------------------------------

    def _build_dictionary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.dict_enabled_check = QCheckBox("Wörterbuch in Transkription einspeisen")
        self.dict_enabled_check.setChecked(bool(self.config.get("dictionary_enabled")))
        layout.addWidget(self.dict_enabled_check)

        learn_row = QHBoxLayout()
        self.dict_learning_check = QCheckBox("Aus Korrekturen lernen, Schwelle:")
        self.dict_learning_check.setChecked(bool(self.config.get("dictionary_learning_enabled")))
        learn_row.addWidget(self.dict_learning_check)
        self.learn_threshold_spin = QSpinBox()
        self.learn_threshold_spin.setRange(1, 10)
        self.learn_threshold_spin.setSuffix("× gleiche Korrektur")
        self.learn_threshold_spin.setValue(int(self.config.get("dictionary_learn_threshold")))
        learn_row.addWidget(self.learn_threshold_spin)
        learn_row.addStretch()
        layout.addLayout(learn_row)

        terms_group = QGroupBox("Begriffe (Fachwörter, Namen, Abkürzungen)")
        terms_layout = QVBoxLayout(terms_group)
        self.terms_listing = QListWidget()
        self.terms_listing.setMaximumHeight(90)
        terms_layout.addWidget(self.terms_listing)
        terms_row = QHBoxLayout()
        add_term_btn = QPushButton("Hinzufügen...")
        add_term_btn.clicked.connect(self._on_add_term)
        terms_row.addWidget(add_term_btn)
        remove_term_btn = QPushButton("Entfernen")
        remove_term_btn.clicked.connect(self._on_remove_term)
        terms_row.addWidget(remove_term_btn)
        terms_row.addStretch()
        terms_layout.addLayout(terms_row)
        layout.addWidget(terms_group)

        corr_group = QGroupBox("Korrekturen (falsch → richtig)")
        corr_layout = QVBoxLayout(corr_group)
        self.corr_table = QTableWidget(0, 4)
        self.corr_table.setHorizontalHeaderLabels(["Falsch", "Richtig", "Quelle", "Anzahl"])
        self.corr_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.corr_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.corr_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.corr_table.setEditTriggers(QTableWidget.NoEditTriggers)
        corr_layout.addWidget(self.corr_table)
        corr_row = QHBoxLayout()
        add_corr_btn = QPushButton("Hinzufügen...")
        add_corr_btn.clicked.connect(self._on_add_correction)
        corr_row.addWidget(add_corr_btn)
        remove_corr_btn = QPushButton("Entfernen")
        remove_corr_btn.clicked.connect(self._on_remove_correction)
        corr_row.addWidget(remove_corr_btn)
        corr_row.addStretch()
        corr_layout.addLayout(corr_row)
        layout.addWidget(corr_group)

        self._refresh_dictionary_views()
        return tab

    def _refresh_dictionary_views(self):
        d = self.app.dictionary
        self.terms_listing.clear()
        for term in d.terms:
            self.terms_listing.addItem(term)
        corrections = d.corrections()
        self.corr_table.setRowCount(len(corrections))
        source_labels = {"learned": "gelernt", "manual": "manuell"}
        for row, corr in enumerate(corrections):
            self.corr_table.setItem(row, 0, QTableWidgetItem(corr.wrong))
            self.corr_table.setItem(row, 1, QTableWidgetItem(corr.right))
            self.corr_table.setItem(row, 2, QTableWidgetItem(
                source_labels.get(corr.source, corr.source)))
            self.corr_table.setItem(row, 3, QTableWidgetItem(str(corr.count)))

    def _on_add_term(self):
        text, ok = QInputDialog.getText(self, "Begriff hinzufügen",
                                        "Fachbegriff / Name / Abkürzung:")
        if ok and text.strip():
            self.app.dictionary.add_term(text.strip())
            self._refresh_dictionary_views()

    def _on_remove_term(self):
        item = self.terms_listing.currentItem()
        if item is not None:
            self.app.dictionary.remove_term(item.text())
            self._refresh_dictionary_views()

    def _on_add_correction(self):
        wrong, ok = QInputDialog.getText(self, "Korrektur hinzufügen",
                                         "Falsch transkribiert als:")
        if not ok or not wrong.strip():
            return
        right, ok = QInputDialog.getText(self, "Korrektur hinzufügen",
                                         "Soll ersetzt werden durch:")
        if not ok or not right.strip():
            return
        self.app.dictionary.add_correction(wrong.strip(), right.strip(), source="manual")
        self._refresh_dictionary_views()

    def _on_remove_correction(self):
        row = self.corr_table.currentRow()
        if row < 0:
            return
        wrong_item = self.corr_table.item(row, 0)
        if wrong_item is not None:
            self.app.dictionary.remove_correction(wrong_item.text())
            self._refresh_dictionary_views()

    # -- Tab: Statistik ---------------------------------------------------------------

    def _build_stats_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.stats_label = QLabel()
        self.stats_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.stats_label)
        self._refresh_stats_label()

        form = QFormLayout()
        self.stats_enabled_check = QCheckBox("Statistik erfassen")
        self.stats_enabled_check.setChecked(bool(self.config.get("stats_enabled")))
        form.addRow("", self.stats_enabled_check)

        self.wpm_spin = QSpinBox()
        self.wpm_spin.setRange(10, 200)
        self.wpm_spin.setSuffix(" WPM")
        self.wpm_spin.setValue(int(self.config.get("typing_wpm")))
        self.wpm_spin.setToolTip("Angenommene Tippgeschwindigkeit für die Ersparnis-Berechnung")
        form.addRow("Tippgeschwindigkeit (Vergleich):", self.wpm_spin)
        layout.addLayout(form)

        reset_btn = QPushButton("Statistik zurücksetzen")
        reset_btn.clicked.connect(self._on_reset_stats)
        layout.addWidget(reset_btn)
        layout.addStretch()
        return tab

    def _refresh_stats_label(self):
        s = self.app.stats.summary()
        self.stats_label.setText(
            "<h3>≈ {:.0f} Minuten gespart</h3>"
            "<p>{} Wörter in {} Diktaten ({:.1f} Min Sprechzeit)<br>"
            "Gemessene Sprechrate: {:.0f} WPM · Vergleichsbasis: {:.0f} WPM tippen</p>".format(
                s["total_saved_minutes"], s["total_words"], s["total_dictations"],
                s["total_speech_minutes"], s["avg_spoken_wpm"], s["typing_wpm"]))

    def _on_reset_stats(self):
        answer = QMessageBox.question(self, "Statistik zurücksetzen",
                                      "Alle erfassten Werte löschen?")
        if answer == QMessageBox.Yes:
            self.app.stats.reset()
            self._refresh_stats_label()
            self.app.tray.refresh_stats_label()

    # -- Tab: System ----------------------------------------------------------------------

    def _build_system_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.autostart_check = QCheckBox("Bei Systemstart automatisch starten")
        self.autostart_check.setChecked(autostart.is_enabled())
        layout.addWidget(self.autostart_check)

        if self.app.hotkey_warning:
            warn = QLabel("⚠ " + self.app.hotkey_warning)
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #b8860b;")
            layout.addWidget(warn)

        layout.addStretch()
        return tab

    # -- Speichern ---------------------------------------------------------------------------

    def _on_save(self):
        old = {k: self.config.get(k) for k in
               ("backend", "model_size", "device", "compute_type", "language")}

        self.config.update({
            "mode": self.mode_combo.currentData(),
            "live_inject": self.inject_combo.currentData(),
            "language": None if self.lang_combo.currentData() == "auto"
                        else self.lang_combo.currentData(),
            "show_overlay": self.overlay_check.isChecked(),
            "input_device": self.device_combo.currentData(),
            "trigger_keys": list(self._trigger_list),
            "hold_threshold": self.hold_spin.value(),
            "double_tap_enabled": self.double_tap_check.isChecked(),
            "backend": self.backend_combo.currentData(),
            "model_size": self.model_combo.currentData(),
            "device": self.device_hw_combo.currentData(),
            "compute_type": self.compute_combo.currentData(),
            "live_preview_interval": self.preview_spin.value(),
            "vad_silence_ms": self.silence_spin.value(),
            "dictionary_enabled": self.dict_enabled_check.isChecked(),
            "dictionary_learning_enabled": self.dict_learning_check.isChecked(),
            "dictionary_learn_threshold": self.learn_threshold_spin.value(),
            "stats_enabled": self.stats_enabled_check.isChecked(),
            "typing_wpm": self.wpm_spin.value(),
            "autostart": self.autostart_check.isChecked(),
        })

        autostart.set_enabled(self.autostart_check.isChecked())

        model_changed = any(
            old[k] != self.config.get(k)
            for k in ("backend", "model_size", "device", "compute_type"))
        self.app.apply_settings(model_changed=model_changed)
        self.accept()
