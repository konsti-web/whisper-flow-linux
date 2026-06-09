# -*- coding: utf-8 -*-
"""TranscriptionService: laedt das passende Backend und transkribiert.

Verantwortlich fuer:
  - Aufloesen der "auto"-Einstellungen ueber die Hardware-Erkennung
  - CPU-Fallback, wenn das GPU-Backend nicht laedt
  - Warmup nach dem Laden (reduziert die Latenz des ersten Diktats)
  - Einspeisen des Woerterbuchs (Hotwords bzw. Initial-Prompt)
  - Anwenden der gelernten Korrekturen auf das Ergebnis
"""

import threading
import time

import numpy as np

from whisperflow.config import safe_print
from whisperflow.hardware import auto_select
from whisperflow.transcribe import create_backend
from whisperflow.transcribe.base import BackendNotAvailable, TranscriptOptions


class TranscriptionService:
    def __init__(self, config, dictionary=None):
        self.config = config
        self.dictionary = dictionary
        self.backend = None
        self._lock = threading.Lock()  # nur eine Transkription gleichzeitig
        self.load_error = None
        self.load_hint = ""

    @property
    def loaded(self) -> bool:
        return self.backend is not None and self.backend.loaded

    def describe(self) -> str:
        return self.backend.describe() if self.backend else "nicht geladen"

    @property
    def device_label(self) -> str:
        return self.backend.device_label if self.backend else "?"

    # -- Laden ---------------------------------------------------------------

    def load(self) -> bool:
        """Laedt das Backend laut Konfiguration/Empfehlung (blockierend).

        Returns:
            True bei Erfolg. Bei Fehlschlag stehen load_error/load_hint bereit.
        """
        self.load_error = None
        self.load_hint = ""
        rec = auto_select(self.config)

        attempts = [(rec.backend, rec.device, rec.compute_type, rec.model_size)]
        if rec.device != "cpu":
            # Fallback: gleiches Backend auf CPU
            attempts.append((rec.backend, "cpu", "int8", rec.model_size))
            # Letzte Rettung: faster-whisper CPU mit kleinem Modell
            if rec.backend != "faster-whisper":
                attempts.append(("faster-whisper", "cpu", "int8", "small"))

        last_error, last_hint = None, ""
        for backend_name, device, compute, model in attempts:
            safe_print("[MODELL] Lade '{}' auf {} ({}) [{}]...".format(
                model, device, compute, backend_name))
            try:
                t0 = time.time()
                backend = create_backend(backend_name, model, device, compute)
                backend.load()
                with self._lock:
                    old = self.backend
                    self.backend = backend
                if old is not None:
                    old.unload()
                safe_print("[MODELL] Geladen in {:.1f}s ({})".format(
                    time.time() - t0, backend.describe()))
                self._warmup()
                if (backend_name, device) != (rec.backend, rec.device):
                    self.load_hint = ("'{}' auf {} nicht verfuegbar - Fallback auf {} ({})".format(
                        rec.backend, rec.device, backend.name, backend.device_label))
                return True
            except BackendNotAvailable as e:
                last_error, last_hint = str(e), e.hint
                safe_print("[MODELL] {} - {}".format(e, e.hint))
            except Exception as e:
                last_error = "Modell laden fehlgeschlagen ({} auf {}): {}".format(
                    backend_name, device, e)
                last_hint = self._hint_for_load_error(device, e)
                safe_print("[MODELL] {}".format(last_error))

        self.load_error = last_error or "Kein Backend verfuegbar"
        self.load_hint = last_hint or "Installation pruefen: pip install faster-whisper"
        return False

    @staticmethod
    def _hint_for_load_error(device, error) -> str:
        text = str(error).lower()
        if device == "cuda" and ("cuda" in text or "cublas" in text or "cudnn" in text):
            return ("NVIDIA-Treiber pruefen (nvidia-smi). CUDA-Bibliotheken kommen per pip; "
                    "ggf. run.sh verwenden, das LD_LIBRARY_PATH setzt.")
        if "download" in text or "connection" in text or "http" in text:
            return "Modell-Download fehlgeschlagen - Internetverbindung pruefen (nur beim ersten Mal noetig)."
        if "memory" in text or "alloc" in text:
            return "Zu wenig Speicher - kleineres Modell in den Einstellungen waehlen."
        return "Kleineres Modell oder anderes Backend in den Einstellungen versuchen."

    def _warmup(self):
        """Transkribiert kurz Stille, damit Kernel/Caches initialisiert sind."""
        try:
            silence = np.zeros(int(0.4 * 16000), dtype=np.float32)
            self.transcribe(silence, is_stream_segment=True, apply_dictionary=False)
            safe_print("[MODELL] Warmup abgeschlossen")
        except Exception:
            pass

    def reload(self) -> bool:
        """Laedt das Backend neu (z. B. nach Einstellungsaenderung)."""
        with self._lock:
            if self.backend is not None:
                self.backend.unload()
                self.backend = None
        return self.load()

    def unload(self):
        with self._lock:
            if self.backend is not None:
                self.backend.unload()
                self.backend = None

    # -- Transkription ---------------------------------------------------------

    def _build_options(self, is_stream_segment: bool) -> TranscriptOptions:
        opts = TranscriptOptions(
            language=self.config.get("language"),
            beam_size=1,
            # VAD-geschnittene Segmente nicht erneut filtern (frisst kurze Segmente)
            vad_filter=not is_stream_segment,
        )
        if (self.dictionary is not None and self.config.get("dictionary_enabled")
                and self.config.get("dictionary_use_prompt")):
            if self.backend is not None and self.backend.supports_hotwords:
                opts.hotwords = self.dictionary.hotwords() or None
            else:
                opts.initial_prompt = self.dictionary.initial_prompt() or None
        return opts

    def transcribe(self, audio: np.ndarray, is_stream_segment: bool = False,
                   apply_dictionary: bool = True) -> str:
        """Transkribiert float32-Audio @ 16 kHz; wendet das Woerterbuch an."""
        if self.backend is None or not self.backend.loaded:
            raise RuntimeError("Modell ist noch nicht geladen")
        if audio.size < int(0.15 * 16000):
            return ""
        opts = self._build_options(is_stream_segment)
        with self._lock:
            text = self.backend.transcribe(audio, opts)
        text = (text or "").strip()
        if text and apply_dictionary and self.dictionary is not None \
                and self.config.get("dictionary_enabled"):
            text = self.dictionary.apply_corrections(text)
        return text
