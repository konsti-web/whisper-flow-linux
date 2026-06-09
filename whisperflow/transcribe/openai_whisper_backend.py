# -*- coding: utf-8 -*-
"""openai-whisper-Backend (PyTorch): primaer fuer AMD-GPUs mit ROCm.

PyTorch/ROCm meldet sich als 'cuda'-Device, daher funktioniert der
bestehende AMD-Workflow unveraendert weiter.
"""

import numpy as np

from whisperflow.transcribe.base import BackendNotAvailable, TranscriptionBackend, TranscriptOptions


class OpenAIWhisperBackend(TranscriptionBackend):
    name = "openai-whisper"
    supports_hotwords = False

    def load(self):
        try:
            import whisper
        except ImportError as e:
            raise BackendNotAvailable(
                "openai-whisper ist nicht installiert: {}".format(e),
                hint=("Installieren mit: pip install openai-whisper  "
                      "(AMD: pip install torch --index-url https://download.pytorch.org/whl/rocm6.2)"))

        device = "cuda" if self.device in ("cuda", "metal", "vulkan") else "cpu"
        try:
            import torch
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
        except ImportError:
            device = "cpu"

        self.model = whisper.load_model(self.model_size, device=device)
        self.device = device

    def transcribe(self, audio: np.ndarray, opts: TranscriptOptions) -> str:
        result = self.model.transcribe(
            audio.astype(np.float32),
            language=opts.language,
            beam_size=opts.beam_size,
            condition_on_previous_text=False,
            initial_prompt=opts.initial_prompt,
            fp16=(self.device != "cpu"),
        )
        return (result.get("text") or "").strip()
