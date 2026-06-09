# -*- coding: utf-8 -*-
"""faster-whisper-Backend (CTranslate2): CUDA und CPU."""

import numpy as np

from whisperflow.transcribe.base import BackendNotAvailable, TranscriptionBackend, TranscriptOptions


class FasterWhisperBackend(TranscriptionBackend):
    name = "faster-whisper"
    supports_hotwords = True

    def load(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise BackendNotAvailable(
                "faster-whisper ist nicht installiert: {}".format(e),
                hint="Installieren mit: pip install faster-whisper")

        device = self.device
        if device in ("metal", "vulkan"):
            # CTranslate2 kennt nur cuda/cpu - auf CPU ausweichen
            device = "cpu"
        compute = self.compute_type
        if compute in ("auto", "default", "", None):
            compute = "float16" if device == "cuda" else "int8"

        self.model = WhisperModel(self.model_size, device=device, compute_type=compute)
        self.device = device
        self.compute_type = compute

    def transcribe(self, audio: np.ndarray, opts: TranscriptOptions) -> str:
        segments, _info = self.model.transcribe(
            audio,
            language=opts.language,
            beam_size=opts.beam_size,
            vad_filter=opts.vad_filter,
            condition_on_previous_text=False,
            initial_prompt=opts.initial_prompt,
            hotwords=opts.hotwords,
        )
        parts = []
        for segment in segments:
            if segment.text:
                parts.append(segment.text)
        return " ".join(p.strip() for p in parts).strip()
