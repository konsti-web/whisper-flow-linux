#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kompatibilitaets-Einstieg: startet die Cross-Platform-App.

Die fruehere GTK-Monolith-Implementierung lebt jetzt modular im
whisperflow-Paket (siehe whisperflow/app.py). run.sh, Desktop-Dateien
und der whisper-flow-Befehl funktionieren unveraendert.
"""

import sys

if __name__ == "__main__":
    from whisperflow.app import main
    sys.exit(main())
