; Inno Setup script: builds dist\UniRGB-Setup-<version>.exe from dist\UniRGB.exe.
; Per-user install, no admin prompt. User settings in %APPDATA%\UniRGB are kept on uninstall.
#define AppVersion "0.1.0"

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

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\UniRGB.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"
Source: "..\README.md"; DestDir: "{app}"

[Icons]
Name: "{group}\UniRGB"; Filename: "{app}\UniRGB.exe"
Name: "{group}\Uninstall UniRGB"; Filename: "{uninstallexe}"
Name: "{autodesktop}\UniRGB"; Filename: "{app}\UniRGB.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UniRGB.exe"; Description: "Start UniRGB"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; stop a running UniRGB so its files can be removed
Filename: "{sys}\taskkill.exe"; Parameters: "/IM UniRGB.exe /F"; Flags: runhidden; RunOnceId: "StopUniRGB"
