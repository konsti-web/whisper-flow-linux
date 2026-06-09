# -*- coding: utf-8 -*-
"""Gemeinsames Interface aller Transkriptions-Backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


class BackendNotAvailable(Exception):
    """Backend nicht installiert oder nicht ladbar (mit Loesungshinweis)."""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


@dataclass
class TranscriptOptions:
    language: Optional[str] = None        # None = automatisch
    initial_prompt: Optional[str] = None  # Woerterbuch-Begriffe als Prompt
    hotwords: Optional[str] = None        # nur faster-whisper
    beam_size: int = 1
    vad_filter: bool = True               # fuer VAD-geschnittene Segmente: False


class TranscriptionBackend(ABC):
    """Ein geladenes Whisper-Modell auf einem konkreten Geraet."""

    name = "base"
    supports_hotwords = False

    def __init__(self, model_size: str, device: str, compute_type: str):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None

    @abstractmethod
    def load(self):
        """Laedt das Modell. Wirft BackendNotAvailable oder RuntimeError."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, opts: TranscriptOptions) -> str:
        """Transkribiert float32-Audio @ 16 kHz zu Text."""

    def unload(self):
        self.model = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    @property
    def device_label(self) -> str:
        labels = {"cuda": "GPU (CUDA)", "metal": "GPU (Metal)",
                  "vulkan": "GPU (Vulkan)", "cpu": "CPU"}
        return labels.get(self.device, self.device)

    def describe(self) -> str:
        return "{} / {} / {}".format(self.name, self.model_size, self.device_label)
