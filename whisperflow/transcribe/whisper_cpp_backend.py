# -*- coding: utf-8 -*-
"""whisper.cpp-Backend (pywhispercpp): Metal auf macOS, Vulkan fuer AMD/Intel-GPUs.

whisper.cpp nutzt die GPU automatisch, wenn es mit Metal/Vulkan kompiliert
wurde, und faellt sonst intern auf die CPU zurueck. Modelle werden beim
ersten Laden automatisch heruntergeladen (ggml-Format).
"""

import os

import numpy as np

from whisperflow.transcribe.base import BackendNotAvailable, TranscriptionBackend, TranscriptOptions

# Mapping unserer Modellnamen auf whisper.cpp/ggml-Namen
_MODEL_MAP = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large-v3": "large-v3",
    "large-v3-turbo": "large-v3-turbo",
}


class WhisperCppBackend(TranscriptionBackend):
    name = "whisper-cpp"
    supports_hotwords = False

    def load(self):
        try:
            from pywhispercpp.model import Model
        except ImportError as e:
            raise BackendNotAvailable(
                "pywhispercpp ist nicht installiert: {}".format(e),
                hint=("Installieren mit: pip install pywhispercpp  "
                      "(fuer Vulkan: GGML_VULKAN=1 pip install pywhispercpp --no-binary pywhispercpp)"))

        model_name = _MODEL_MAP.get(self.model_size, self.model_size)
        n_threads = max(2, (os.cpu_count() or 4) - 1)

        # use_gpu nur uebergeben, wenn die installierte Version es kennt
        kwargs = {"n_threads": n_threads, "print_progress": False, "print_realtime": False}
        try:
            self.model = Model(model_name, use_gpu=(self.device != "cpu"), **kwargs)
        except TypeError:
            self.model = Model(model_name, **kwargs)

    def transcribe(self, audio: np.ndarray, opts: TranscriptOptions) -> str:
        kwargs = {"language": opts.language or "auto"}
        if opts.initial_prompt:
            kwargs["initial_prompt"] = opts.initial_prompt
        try:
            segments = self.model.transcribe(audio.astype(np.float32), **kwargs)
        except TypeError:
            # Aeltere pywhispercpp-Versionen kennen initial_prompt nicht
            kwargs.pop("initial_prompt", None)
            segments = self.model.transcribe(audio.astype(np.float32), **kwargs)
        parts = [seg.text for seg in segments if getattr(seg, "text", "")]
        return " ".join(p.strip() for p in parts).strip()
