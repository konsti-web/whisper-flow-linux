# Flatpak-Paketierung - Hinweise und Einschraenkungen

Whisper Flow ist eine System-Utility, die zwei Dinge tut, die der
Flatpak-Sandbox-Philosophie widersprechen:

1. **Globale Hotkeys** - die App muss Tastendruecke sehen, waehrend ein
   beliebiges anderes Fenster fokussiert ist. In der Sandbox geht das nur
   ueber `--device=all` (direkter `/dev/input`-Zugriff, evdev-Backend)
   plus Mitgliedschaft des Nutzers in der Gruppe `input`. Das XDG-Portal
   `GlobalShortcuts` waere der saubere Weg, ist aber noch nicht auf allen
   Desktops verfuegbar.
2. **Texteinfuegen in fremde Fenster** - unter Wayland braucht es `wtype`
   oder `ydotool` **auf dem Host**; aus der Sandbox heraus funktioniert nur
   das Setzen der Zwischenablage zuverlaessig. Der Nutzer fuegt dann mit
   Strg+V ein (die App zeigt eine Benachrichtigung).

**Empfehlung:** AppImage oder native Installation (install.sh) fuer volle
Funktionalitaet; Flatpak fuer Nutzer, die mit Clipboard-Einfuegen und
evdev-Ausnahme leben koennen.

## Bauen

```bash
# Runtime installieren
flatpak install flathub org.kde.Platform//6.7 org.kde.Sdk//6.7

# Bauen und installieren (Netzwerk-Build, fuer lokale Nutzung)
flatpak-builder --user --install --force-clean build-flatpak \
    packaging/flatpak/io.github.konsti_web.WhisperFlow.yaml

flatpak run io.github.konsti_web.WhisperFlow
```

Fuer eine Flathub-Einreichung muessen die pip-Abhaengigkeiten als
Offline-Quellen generiert werden (`flatpak-pip-generator` aus
https://github.com/flatpak/flatpak-builder-tools), da Flathub-Builds
kein Netzwerk haben. PySide6 kommt dann sinnvollerweise aus dem
`com.riverbankcomputing.PyQt.BaseApp`-Pendant bzw. als Wheel-Quelle.
