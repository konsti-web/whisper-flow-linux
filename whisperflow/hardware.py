# -*- coding: utf-8 -*-
"""Hardware-Erkennung und automatische Backend-/Modell-Wahl.

Erkennung (detect_hardware) und Empfehlung (recommend) sind bewusst
getrennt: Die Empfehlung ist eine reine Funktion ueber HardwareInfo und
damit ohne echte Hardware testbar.

Backend-Matrix:
  - macOS Apple Silicon  -> whisper.cpp (Metal), sonst CPU
  - NVIDIA-GPU           -> faster-whisper (CUDA)
  - AMD-GPU mit ROCm     -> openai-whisper (PyTorch/ROCm)
  - AMD/Intel/sonstige   -> whisper.cpp (Vulkan)
  - Fallback             -> faster-whisper (CPU, int8)
"""

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from whisperflow.config import safe_print

# Modellgroessen, sortiert von klein nach gross
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]


@dataclass
class GpuInfo:
    vendor: str            # "nvidia" | "amd" | "intel" | "apple" | "other"
    name: str = ""
    vram_mb: int = 0       # 0 = unbekannt


@dataclass
class HardwareInfo:
    os_name: str           # "Linux" | "Darwin" | "Windows"
    arch: str              # "x86_64" | "arm64" | ...
    ram_gb: float = 8.0
    cpu_cores: int = 4
    gpus: List[GpuInfo] = field(default_factory=list)
    has_rocm: bool = False
    has_vulkan: bool = False

    def first_gpu(self, vendor: str) -> Optional[GpuInfo]:
        for gpu in self.gpus:
            if gpu.vendor == vendor:
                return gpu
        return None

    def describe(self) -> str:
        parts = ["{} {}".format(self.os_name, self.arch),
                 "{:.0f} GB RAM".format(self.ram_gb),
                 "{} Kerne".format(self.cpu_cores)]
        for gpu in self.gpus:
            label = gpu.name or gpu.vendor.upper()
            if gpu.vram_mb:
                label += " ({:.1f} GB VRAM)".format(gpu.vram_mb / 1024.0)
            parts.append(label)
        return ", ".join(parts)


@dataclass
class Recommendation:
    backend: str           # "faster-whisper" | "whisper-cpp" | "openai-whisper"
    device: str            # "cuda" | "cpu" | "metal" | "vulkan"
    compute_type: str      # nur fuer faster-whisper relevant, sonst "default"
    model_size: str
    reason: str = ""


# ---------------------------------------------------------------------------
# Erkennung (echte Probes mit Fallbacks)
# ---------------------------------------------------------------------------

def _detect_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024 ** 2)
    except Exception:
        pass
    return 8.0


def _detect_cpu_cores() -> int:
    return os.cpu_count() or 4


def parse_nvidia_smi(output: str) -> List[GpuInfo]:
    """Parst `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader`."""
    gpus = []
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        vram_mb = 0
        if len(parts) >= 2:
            m = re.search(r"(\d+)", parts[1])
            if m:
                vram_mb = int(m.group(1))
        gpus.append(GpuInfo(vendor="nvidia", name=parts[0], vram_mb=vram_mb))
    return gpus


def _detect_nvidia() -> List[GpuInfo]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return parse_nvidia_smi(result.stdout)
    except Exception:
        pass
    return []


# PCI-Vendor-IDs fuer /sys/class/drm
_PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def _detect_linux_gpus() -> List[GpuInfo]:
    gpus = []
    try:
        drm = "/sys/class/drm"
        for entry in sorted(os.listdir(drm)):
            # Nur Haupteintraege (card0, card1, ...), keine Connectors (card0-HDMI-..)
            if not re.fullmatch(r"card\d+", entry):
                continue
            vendor_file = os.path.join(drm, entry, "device", "vendor")
            try:
                with open(vendor_file, "r") as f:
                    vendor_id = f.read().strip().lower()
                vendor = _PCI_VENDORS.get(vendor_id, "other")
                gpus.append(GpuInfo(vendor=vendor))
            except OSError:
                continue
    except OSError:
        pass
    return gpus


def _detect_windows_gpus() -> List[GpuInfo]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController).Name"],
            capture_output=True, text=True, timeout=10)
        gpus = []
        for line in result.stdout.strip().splitlines():
            name = line.strip()
            if not name:
                continue
            low = name.lower()
            if "nvidia" in low or "geforce" in low or "quadro" in low:
                vendor = "nvidia"
            elif "amd" in low or "radeon" in low:
                vendor = "amd"
            elif "intel" in low:
                vendor = "intel"
            else:
                vendor = "other"
            gpus.append(GpuInfo(vendor=vendor, name=name))
        return gpus
    except Exception:
        return []


def _detect_vulkan(os_name: str) -> bool:
    if os_name == "Linux":
        if shutil.which("vulkaninfo"):
            return True
        for d in ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d",
                  "/usr/local/share/vulkan/icd.d"):
            try:
                if os.path.isdir(d) and os.listdir(d):
                    return True
            except OSError:
                continue
        return False
    if os_name == "Windows":
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        return os.path.exists(os.path.join(system32, "vulkan-1.dll"))
    return False


def _detect_rocm() -> bool:
    if shutil.which("rocminfo") or os.path.isdir("/opt/rocm"):
        return True
    try:
        import torch
        return bool(getattr(torch.version, "hip", None))
    except Exception:
        return False


def detect_hardware() -> HardwareInfo:
    """Erkennt OS, RAM, CPU und GPUs der laufenden Maschine."""
    os_name = platform.system()
    arch = platform.machine()
    hw = HardwareInfo(
        os_name=os_name,
        arch=arch,
        ram_gb=_detect_ram_gb(),
        cpu_cores=_detect_cpu_cores(),
    )

    if os_name == "Darwin":
        if arch in ("arm64", "aarch64"):
            # Apple Silicon: Unified Memory = RAM
            hw.gpus.append(GpuInfo(vendor="apple", name="Apple Silicon GPU",
                                   vram_mb=int(hw.ram_gb * 1024)))
        return hw

    nvidia = _detect_nvidia()
    hw.gpus.extend(nvidia)

    if os_name == "Linux":
        for gpu in _detect_linux_gpus():
            # NVIDIA kommt bereits praeziser von nvidia-smi
            if gpu.vendor != "nvidia" or not nvidia:
                hw.gpus.append(gpu)
        hw.has_rocm = _detect_rocm()
    elif os_name == "Windows":
        if not nvidia:
            hw.gpus.extend(_detect_windows_gpus())

    hw.has_vulkan = _detect_vulkan(os_name)
    return hw


def available_backends() -> Dict[str, bool]:
    """Prueft (ohne Import der schweren Module), welche Backends installiert sind."""
    import importlib.util
    return {
        "faster-whisper": importlib.util.find_spec("faster_whisper") is not None,
        "whisper-cpp": importlib.util.find_spec("pywhispercpp") is not None,
        "openai-whisper": importlib.util.find_spec("whisper") is not None,
    }


# ---------------------------------------------------------------------------
# Empfehlung (reine Funktion, unit-testbar)
# ---------------------------------------------------------------------------

def _cpu_fallback(hw: HardwareInfo, backends: Dict[str, bool]) -> Recommendation:
    if hw.cpu_cores >= 8 and hw.ram_gb >= 8:
        model = "small"
    elif hw.ram_gb >= 4:
        model = "base"
    else:
        model = "tiny"

    if backends.get("faster-whisper"):
        backend = "faster-whisper"
    elif backends.get("whisper-cpp"):
        backend = "whisper-cpp"
    else:
        backend = "openai-whisper"
    return Recommendation(
        backend=backend, device="cpu", compute_type="int8", model_size=model,
        reason="Keine nutzbare GPU erkannt - CPU mit {} ({} Kerne, {:.0f} GB RAM)".format(
            model, hw.cpu_cores, hw.ram_gb))


def _nvidia_model(vram_mb: int):
    """Modell/Quantisierung nach VRAM. 0 = unbekannt -> konservativ."""
    if vram_mb >= 7000:
        return "large-v3-turbo", "float16"
    if vram_mb >= 4000 or vram_mb == 0:
        return "large-v3-turbo", "int8_float16"
    if vram_mb >= 2500:
        return "small", "float16"
    return "base", "int8_float16"


def recommend(hw: HardwareInfo, backends: Optional[Dict[str, bool]] = None) -> Recommendation:
    """Waehlt Backend, Geraet, Quantisierung und Modellgroesse fuer die Hardware."""
    if backends is None:
        backends = {"faster-whisper": True, "whisper-cpp": True, "openai-whisper": True}

    # 1) macOS: Metal ueber whisper.cpp (CTranslate2 kann kein Metal)
    if hw.os_name == "Darwin":
        if hw.arch in ("arm64", "aarch64") and backends.get("whisper-cpp"):
            if hw.ram_gb >= 16:
                model = "large-v3-turbo"
            elif hw.ram_gb >= 8:
                model = "small"
            else:
                model = "base"
            return Recommendation(
                backend="whisper-cpp", device="metal", compute_type="default",
                model_size=model,
                reason="Apple Silicon erkannt - whisper.cpp mit Metal ({:.0f} GB RAM)".format(hw.ram_gb))
        return _cpu_fallback(hw, backends)

    # 2) NVIDIA: CUDA ueber faster-whisper (schnellster Pfad)
    nvidia = hw.first_gpu("nvidia")
    if nvidia is not None:
        model, compute = _nvidia_model(nvidia.vram_mb)
        if backends.get("faster-whisper"):
            return Recommendation(
                backend="faster-whisper", device="cuda", compute_type=compute,
                model_size=model,
                reason="NVIDIA-GPU erkannt ({}) - faster-whisper mit CUDA".format(
                    nvidia.name or "unbekannt"))
        if backends.get("openai-whisper"):
            return Recommendation(
                backend="openai-whisper", device="cuda", compute_type="float16",
                model_size=model,
                reason="NVIDIA-GPU erkannt, faster-whisper fehlt - openai-whisper mit CUDA")

    # 3) AMD mit ROCm-Stack: openai-whisper (PyTorch/ROCm)
    if hw.has_rocm and hw.first_gpu("amd") is not None and backends.get("openai-whisper"):
        model = "large-v3-turbo" if hw.ram_gb >= 16 else "small"
        return Recommendation(
            backend="openai-whisper", device="cuda", compute_type="float16",
            model_size=model,
            reason="AMD-GPU mit ROCm erkannt - openai-whisper (PyTorch/ROCm)")

    # 4) Sonstige GPUs (AMD/Intel/...): Vulkan ueber whisper.cpp
    other_gpu = next((g for g in hw.gpus if g.vendor in ("amd", "intel", "other")), None)
    if other_gpu is not None and hw.has_vulkan and backends.get("whisper-cpp"):
        vram = other_gpu.vram_mb
        if vram >= 6000 or (vram == 0 and hw.ram_gb >= 16):
            model = "large-v3-turbo"
        elif vram >= 3000 or hw.ram_gb >= 8:
            model = "small"
        else:
            model = "base"
        return Recommendation(
            backend="whisper-cpp", device="vulkan", compute_type="default",
            model_size=model,
            reason="{}-GPU mit Vulkan erkannt - whisper.cpp".format(other_gpu.vendor.upper()))

    # 5) Fallback: CPU
    return _cpu_fallback(hw, backends)


def auto_select(config) -> Recommendation:
    """Loest 'auto'-Einstellungen anhand der erkannten Hardware auf.

    Manuelle Werte aus der Config haben Vorrang vor der Empfehlung.
    """
    hw = detect_hardware()
    backends = available_backends()
    rec = recommend(hw, backends)
    safe_print("[HARDWARE] {}".format(hw.describe()))
    safe_print("[HARDWARE] Empfehlung: {} / {} / {} / {} ({})".format(
        rec.backend, rec.device, rec.compute_type, rec.model_size, rec.reason))

    backend = config.get("backend")
    device = config.get("device")
    compute = config.get("compute_type")
    model = config.get("model_size")
    return Recommendation(
        backend=rec.backend if backend == "auto" else backend,
        device=rec.device if device == "auto" else device,
        compute_type=rec.compute_type if compute == "auto" else compute,
        model_size=rec.model_size if model == "auto" else model,
        reason=rec.reason,
    )
