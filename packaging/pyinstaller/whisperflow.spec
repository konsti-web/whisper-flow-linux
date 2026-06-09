# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec fuer Whisper Flow (alle Plattformen).

Aufruf aus dem Repo-Root:
    pyinstaller packaging/pyinstaller/whisperflow.spec --noconfirm

Whisper-Modelle werden NICHT gebundelt - sie werden beim ersten Start in
den Nutzer-Cache geladen (wie bei der pip-Installation).
"""

import os
import sys

block_cipher = None

# SPECPATH wird von PyInstaller bereitgestellt (Verzeichnis dieser Datei)
repo_root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
if not os.path.exists(os.path.join(repo_root, "whisper_flow.py")):
    repo_root = os.path.abspath(".")

hiddenimports = [
    # Backends werden lazy importiert - PyInstaller muss sie explizit kennen
    "faster_whisper",
    "ctranslate2",
    "sounddevice",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",
]
if sys.platform.startswith("linux"):
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg"]
    try:
        import evdev  # noqa: F401
        hiddenimports += ["evdev"]
    except ImportError:
        pass
try:
    import pywhispercpp  # noqa: F401
    hiddenimports += ["pywhispercpp", "pywhispercpp.model"]
except ImportError:
    pass

a = Analysis(
    [os.path.join(repo_root, "whisper_flow.py")],
    pathex=[repo_root],
    binaries=[],
    datas=[(os.path.join(repo_root, "assets"), "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="whisperflow",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="WhisperFlow",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="WhisperFlow.app",
        bundle_identifier="com.whisperflow.app",
        info_plist={
            "NSMicrophoneUsageDescription":
                "Whisper Flow transkribiert deine Sprache lokal.",
            "LSUIElement": True,  # nur Tray, kein Dock-Icon
        },
    )
