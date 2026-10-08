; Inno Setup script: per-user install (no admin), Start menu entry, optional start at login.
; iscc /DVersion=0.1.0 packaging\windows\wingmacro.iss   (after PyInstaller has built dist\wingmacro)
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6E0B7C0E-3C8A-4C55-9F0B-5E1E2A7C9D41}
AppName=wingmacro
AppVersion={#Version}
AppPublisher=wingmacro
DefaultDirName={localappdata}\Programs\wingmacro
DefaultGroupName=wingmacro
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=wingmacro-{#Version}-windows-setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\wingmacro.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "autostart"; Description: "Start wingmacro when I log in"

[Files]
Source: "..\..\dist\wingmacro\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\wingmacro"; Filename: "{app}\wingmacro.exe"
Name: "{group}\Uninstall wingmacro"; Filename: "{uninstallexe}"

[Registry]
; same value the tray menu's "Start at login" writes
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "wingmacro"; ValueData: """{app}\wingmacro.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\wingmacro.exe"; Description: "Start wingmacro now"; Flags: nowait postinstall

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im wingmacro.exe"; Flags: runhidden; RunOnceId: "stop"
; the tray menu's "Start at login" may have set this without the installer task
Filename: "{sys}\reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v wingmacro /f"; Flags: runhidden; RunOnceId: "autostart"

[UninstallDelete]
Type: dirifempty; Name: "{app}"
