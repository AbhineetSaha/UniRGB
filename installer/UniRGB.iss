; Inno Setup script: builds dist\UniRGB-Setup-<version>.exe from the dist\UniRGB folder.
; Per-user install, no admin prompt. User settings in %APPDATA%\UniRGB are kept on uninstall.
#define AppVersion "0.3.0"

[Setup]
AppId={{6011F4D6-4109-4C7D-A61B-BF517C51E308}
AppName=UniRGB
AppVersion={#AppVersion}
AppPublisher=Abhineet Saha
DefaultDirName={autopf}\UniRGB
DefaultGroupName=UniRGB
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=UniRGB-Setup-{#AppVersion}
UninstallDisplayIcon={app}\UniRGB.exe
SetupIconFile=..\unirgb\ui\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[InstallDelete]
; files an older version left in _internal must not mix with this version's
Type: filesandordirs; Name: "{app}\_internal"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start UniRGB in the background when I sign in"

[Files]
Source: "..\dist\UniRGB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"
Source: "..\README.md"; DestDir: "{app}"
; PawnIO installer, module and licences, staged by tools\fetch_pawnio.py (hash-checked). Used only by the
; one-time setup in Settings, if the user turns on a feature that needs the driver.
Source: "..\build\pawnio\*"; DestDir: "{app}\pawnio"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\UniRGB"; Filename: "{app}\UniRGB.exe"
Name: "{group}\Uninstall UniRGB"; Filename: "{uninstallexe}"
Name: "{autodesktop}\UniRGB"; Filename: "{app}\UniRGB.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UniRGB.exe"; Description: "Start UniRGB"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; stop a running UniRGB so its files can be removed
Filename: "{sys}\taskkill.exe"; Parameters: "/IM UniRGB.exe /F"; Flags: runhidden; RunOnceId: "StopUniRGB"
; if the one-time setup ran, remove its scheduled task and the helper in Program Files (one UAC prompt).
; PawnIO stays installed: other programs may use it, and it has its own entry in Apps.
Filename: "{app}\UniRGB.exe"; Parameters: "--system-setup disable"; Verb: "runas"; Flags: shellexec waituntilterminated runhidden; RunOnceId: "RemoveHelper"; Check: HelperInstalled

[Registry]
; per-user autostart, no admin; the Start Menu shortcut opens the window of the running instance
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "UniRGB"; ValueData: """{app}\UniRGB.exe"" --no-window"; Flags: uninsdeletevalue; Tasks: autostart

[Code]
function HelperInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf64}\UniRGB Hardware Helper\UniRGB.exe'));
end;
