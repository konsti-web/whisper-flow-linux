; Inno-Setup-Skript fuer Whisper Flow (Windows)
; Bauen: 1) pyinstaller packaging\pyinstaller\whisperflow.spec --noconfirm
;        2) iscc packaging\windows\installer.iss

#define MyAppName "Whisper Flow"
#define MyAppVersion "2.0.0"
#define MyAppExeName "whisperflow.exe"

[Setup]
AppId={{8F2B1C64-7A55-4E1B-9C2D-WhisperFlow}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\WhisperFlow
DefaultGroupName={#MyAppName}
OutputDir=..\..\dist
OutputBaseFilename=WhisperFlow-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\WhisperFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Tasks]
Name: "autostart"; Description: "Beim Windows-Start automatisch starten"; \
    GroupDescription: "Autostart:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} starten"; \
    Flags: nowait postinstall skipifsilent
