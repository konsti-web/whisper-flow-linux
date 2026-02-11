#!/bin/bash
# Startet Whisper Flow

# Zum Skript-Verzeichnis wechseln (absoluter Pfad)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# WICHTIG: C.UTF-8 Locale - PyAV/FFmpeg hat Probleme mit de_DE
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

if [ ! -d "venv" ]; then
    echo "Virtuelle Umgebung nicht gefunden. Fuehre zuerst install.sh aus."
    exit 1
fi

source venv/bin/activate

# CUDA Bibliotheken Pfad setzen (Python-Version automatisch erkennen)
PYTHON_VERSION=$(python -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")
CUDA_LIBS="$SCRIPT_DIR/venv/lib/$PYTHON_VERSION/site-packages/nvidia"
if [ -d "$CUDA_LIBS" ]; then
    export LD_LIBRARY_PATH="$CUDA_LIBS/cublas/lib:$CUDA_LIBS/cudnn/lib:$LD_LIBRARY_PATH"
fi

exec python whisper_flow.py "$@"
