#!/bin/bash
# Startet Whisper Flow

# Zum Skript-Verzeichnis wechseln (absoluter Pfad)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONIOENCODING=utf-8

if [ ! -d "venv" ]; then
    echo "Virtuelle Umgebung nicht gefunden. Fuehre zuerst install.sh aus."
    exit 1
fi

source venv/bin/activate

# CUDA-Bibliotheken aus pip-Paketen finden (Python-Version automatisch erkennen)
PYTHON_VERSION=$(python -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")
CUDA_LIBS="$SCRIPT_DIR/venv/lib/$PYTHON_VERSION/site-packages/nvidia"
if [ -d "$CUDA_LIBS" ]; then
    export LD_LIBRARY_PATH="$CUDA_LIBS/cublas/lib:$CUDA_LIBS/cudnn/lib:$LD_LIBRARY_PATH"
fi

# ROCm-Workaround fuer nicht offiziell unterstuetzte AMD GPUs (z.B. iGPUs)
if python -c "import torch; exit(0 if hasattr(torch.version, 'hip') and torch.version.hip else 1)" 2>/dev/null; then
    [ -d "/opt/rocm/lib" ] && export LD_LIBRARY_PATH="/opt/rocm/lib:$LD_LIBRARY_PATH"
    export HSA_OVERRIDE_GFX_VERSION=${HSA_OVERRIDE_GFX_VERSION:-11.0.0}
fi

exec python whisper_flow.py "$@"
