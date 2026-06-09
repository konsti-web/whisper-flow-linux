# -*- coding: utf-8 -*-
"""Tests fuer Hardware-Erkennung und Backend-/Modell-Empfehlung.

Deckt die Akzeptanz-Matrix ab:
NVIDIA -> CUDA, macOS -> Metal, sonstige GPU -> Vulkan, sonst CPU.
"""

from whisperflow.hardware import (
    GpuInfo,
    HardwareInfo,
    parse_nvidia_smi,
    recommend,
)

ALL_BACKENDS = {"faster-whisper": True, "whisper-cpp": True, "openai-whisper": True}


def _hw(**kwargs):
    defaults = dict(os_name="Linux", arch="x86_64", ram_gb=16.0, cpu_cores=8)
    defaults.update(kwargs)
    return HardwareInfo(**defaults)


# --- Akzeptanz-Matrix -------------------------------------------------------

def test_nvidia_gets_cuda_faster_whisper():
    hw = _hw(gpus=[GpuInfo("nvidia", "RTX 4070", vram_mb=12282)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.backend == "faster-whisper"
    assert rec.device == "cuda"
    assert rec.model_size == "large-v3-turbo"
    assert rec.compute_type == "float16"


def test_macos_apple_silicon_gets_metal():
    hw = _hw(os_name="Darwin", arch="arm64", ram_gb=16.0,
             gpus=[GpuInfo("apple", "Apple M2", vram_mb=16384)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.backend == "whisper-cpp"
    assert rec.device == "metal"
    assert rec.model_size == "large-v3-turbo"


def test_amd_gpu_gets_vulkan():
    hw = _hw(gpus=[GpuInfo("amd", "RX 6700", vram_mb=0)], has_vulkan=True)
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.backend == "whisper-cpp"
    assert rec.device == "vulkan"


def test_intel_gpu_gets_vulkan():
    hw = _hw(gpus=[GpuInfo("intel", "Arc A750", vram_mb=8192)], has_vulkan=True)
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.device == "vulkan"
    assert rec.model_size == "large-v3-turbo"


def test_no_gpu_falls_back_to_cpu():
    hw = _hw(gpus=[])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.device == "cpu"
    assert rec.backend == "faster-whisper"
    assert rec.compute_type == "int8"


# --- Modell-/Quantisierungs-Matrix -------------------------------------------

def test_nvidia_small_vram_gets_smaller_model():
    hw = _hw(gpus=[GpuInfo("nvidia", "GTX 1650", vram_mb=4096)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.model_size == "large-v3-turbo"
    assert rec.compute_type == "int8_float16"

    hw = _hw(gpus=[GpuInfo("nvidia", "GTX 1050", vram_mb=3000)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.model_size == "small"

    hw = _hw(gpus=[GpuInfo("nvidia", "MX150", vram_mb=2048)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.model_size == "base"


def test_cpu_model_scales_with_hardware():
    strong = _hw(gpus=[], cpu_cores=16, ram_gb=32)
    assert recommend(strong, ALL_BACKENDS).model_size == "small"

    medium = _hw(gpus=[], cpu_cores=4, ram_gb=8)
    assert recommend(medium, ALL_BACKENDS).model_size == "base"

    weak = _hw(gpus=[], cpu_cores=2, ram_gb=2)
    assert recommend(weak, ALL_BACKENDS).model_size == "tiny"


def test_mac_low_ram_gets_smaller_model():
    hw = _hw(os_name="Darwin", arch="arm64", ram_gb=8.0,
             gpus=[GpuInfo("apple", vram_mb=8192)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.device == "metal"
    assert rec.model_size == "small"


# --- Fallbacks bei fehlenden Backends ------------------------------------------

def test_nvidia_without_faster_whisper_uses_openai_whisper():
    hw = _hw(gpus=[GpuInfo("nvidia", vram_mb=8192)])
    backends = {"faster-whisper": False, "whisper-cpp": True, "openai-whisper": True}
    rec = recommend(hw, backends)
    assert rec.backend == "openai-whisper"
    assert rec.device == "cuda"


def test_mac_without_pywhispercpp_uses_cpu():
    hw = _hw(os_name="Darwin", arch="arm64", ram_gb=16,
             gpus=[GpuInfo("apple", vram_mb=16384)])
    backends = {"faster-whisper": True, "whisper-cpp": False, "openai-whisper": False}
    rec = recommend(hw, backends)
    assert rec.backend == "faster-whisper"
    assert rec.device == "cpu"


def test_amd_with_rocm_prefers_openai_whisper():
    hw = _hw(gpus=[GpuInfo("amd", "RX 7900", vram_mb=20480)],
             has_rocm=True, has_vulkan=True)
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.backend == "openai-whisper"
    assert rec.device == "cuda"  # ROCm meldet sich als cuda-Device


def test_amd_without_vulkan_or_rocm_falls_back_to_cpu():
    hw = _hw(gpus=[GpuInfo("amd", vram_mb=8192)], has_vulkan=False, has_rocm=False)
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.device == "cpu"


def test_nvidia_on_darwin_never_recommends_cuda():
    # Hypothetischer Fall: Darwin-Check muss vor NVIDIA greifen
    hw = _hw(os_name="Darwin", arch="x86_64",
             gpus=[GpuInfo("nvidia", vram_mb=4096)])
    rec = recommend(hw, ALL_BACKENDS)
    assert rec.device == "cpu"


# --- nvidia-smi-Parsing -----------------------------------------------------------

def test_parse_nvidia_smi_output():
    output = "NVIDIA GeForce RTX 4070, 12282 MiB\n"
    gpus = parse_nvidia_smi(output)
    assert len(gpus) == 1
    assert gpus[0].vendor == "nvidia"
    assert gpus[0].name == "NVIDIA GeForce RTX 4070"
    assert gpus[0].vram_mb == 12282


def test_parse_nvidia_smi_multi_gpu_and_garbage():
    output = "RTX 3090, 24576 MiB\nRTX 3060, 12288 MiB\n\n"
    gpus = parse_nvidia_smi(output)
    assert [g.vram_mb for g in gpus] == [24576, 12288]


def test_parse_nvidia_smi_empty():
    assert parse_nvidia_smi("") == []
