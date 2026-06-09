# -*- coding: utf-8 -*-
"""Transkriptions-Backends und Streaming-Pipeline."""

from whisperflow.transcribe.base import BackendNotAvailable, TranscriptionBackend, TranscriptOptions


def create_backend(name: str, model_size: str, device: str, compute_type: str) -> TranscriptionBackend:
    """Erzeugt das gewuenschte Backend (Imports passieren erst hier, lazy)."""
    if name == "faster-whisper":
        from whisperflow.transcribe.faster_whisper_backend import FasterWhisperBackend
        return FasterWhisperBackend(model_size, device, compute_type)
    if name == "whisper-cpp":
        from whisperflow.transcribe.whisper_cpp_backend import WhisperCppBackend
        return WhisperCppBackend(model_size, device, compute_type)
    if name == "openai-whisper":
        from whisperflow.transcribe.openai_whisper_backend import OpenAIWhisperBackend
        return OpenAIWhisperBackend(model_size, device, compute_type)
    raise BackendNotAvailable(
        "Unbekanntes Backend '{}'".format(name),
        hint="Gueltige Backends: faster-whisper, whisper-cpp, openai-whisper")
