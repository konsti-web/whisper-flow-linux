# -*- coding: utf-8 -*-
"""Autostart-Verwaltung fuer Linux, macOS und Windows."""

import os
import sys
from pathlib import Path

from whisperflow.config import safe_print

_LINUX_AUTOSTART = Path.home() / ".config" / "autostart" / "whisper-flow.desktop"
_MAC_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.whisperflow.app.plist"
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WIN_VALUE = "WhisperFlow"


def _launch_command() -> str:
    """Kommando, mit dem die App beim Login gestartet wird."""
    # Im Repo-Checkout: run.sh nutzen (setzt venv + LD_LIBRARY_PATH)
    run_sh = Path(__file__).resolve().parent.parent / "run.sh"
    if sys.platform.startswith("linux") and run_sh.exists():
        return str(run_sh)
    if getattr(sys, "frozen", False):
        return sys.executable  # PyInstaller-Bundle
    python = sys.executable
    if sys.platform.startswith("win"):
        pythonw = python.replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw):
            python = pythonw
    return '"{}" -m whisperflow'.format(python)


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _MAC_PLIST.exists()
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
                winreg.QueryValueEx(key, _WIN_VALUE)
            return True
        except OSError:
            return False
    return _LINUX_AUTOSTART.exists()


def set_enabled(enabled: bool) -> bool:
    try:
        if sys.platform == "darwin":
            return _set_macos(enabled)
        if sys.platform.startswith("win"):
            return _set_windows(enabled)
        return _set_linux(enabled)
    except Exception as e:
        safe_print("[AUTOSTART] Fehler: {}".format(e))
        return False


def _set_linux(enabled: bool) -> bool:
    if not enabled:
        _LINUX_AUTOSTART.unlink(missing_ok=True)
        return True
    _LINUX_AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    content = """[Desktop Entry]
Type=Application
Name=Whisper Flow
Comment=Sprache-zu-Text mit Tastendruck
Exec={}
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Audio;
StartupNotify=false
X-GNOME-Autostart-enabled=true
""".format(_launch_command())
    _LINUX_AUTOSTART.write_text(content, encoding="utf-8")
    return True


def _set_macos(enabled: bool) -> bool:
    if not enabled:
        _MAC_PLIST.unlink(missing_ok=True)
        return True
    _MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
    cmd = _launch_command()
    if cmd.startswith('"'):
        program, args = sys.executable, ["-m", "whisperflow"]
    else:
        program, args = cmd, []
    arg_lines = "\n".join(
        "        <string>{}</string>".format(a) for a in [program] + args)
    content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whisperflow.app</string>
    <key>ProgramArguments</key>
    <array>
{}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
""".format(arg_lines)
    _MAC_PLIST.write_text(content, encoding="utf-8")
    return True


def _set_windows(enabled: bool) -> bool:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _WIN_VALUE, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, _WIN_VALUE)
            except OSError:
                pass
    return True
