# -*- coding: utf-8 -*-
"""Aufzaehlung der Audio-Eingabegeraete (sounddevice/PortAudio)."""

from typing import List, Optional

from whisperflow.config import safe_print


def get_input_devices() -> List[dict]:
    """Gibt alle Eingabegeraete zurueck: [{'index','name','channels','rate'}]."""
    devices = []
    try:
        import sounddevice as sd
        for i, info in enumerate(sd.query_devices()):
            try:
                if info.get("max_input_channels", 0) > 0:
                    devices.append({
                        "index": i,
                        "name": str(info.get("name", "Unbekannt")),
                        "channels": int(info.get("max_input_channels", 1)),
                        "rate": int(info.get("default_samplerate", 16000) or 16000),
                    })
            except Exception:
                continue
    except Exception as e:
        safe_print("[WARNUNG] Audiogeraete konnten nicht ermittelt werden: {}".format(e))
    return devices


def get_default_input_name() -> Optional[str]:
    try:
        import sounddevice as sd
        info = sd.query_devices(kind="input")
        return str(info.get("name")) if info else None
    except Exception:
        return None


def find_device_index(name: Optional[str]) -> Optional[int]:
    """Sucht den Index zum konfigurierten Geraetenamen (None = Standard)."""
    if not name:
        return None
    for dev in get_input_devices():
        if dev["name"] == name:
            return dev["index"]
    safe_print("[WARNUNG] Eingabegeraet '{}' nicht gefunden, verwende Standard".format(name))
    return None
