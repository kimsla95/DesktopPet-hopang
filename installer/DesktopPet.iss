; Inno Setup script. Built by tools/release.py:  ISCC /DAppVersion=1.2.3 installer\DesktopPet.iss
; The same installer is used for first install and for updates (AppId keeps them linked).
; User settings live in %APPDATA%\DesktopPet and are never touched by install/update/uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "DesktopPet"
#define AppExe "DesktopPet.exe"

[Setup]
AppId={{8F3C2A51-6B7E-4D2A-9C41-5E7B2D9A1F30}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; close a still-running pet before replacing files
CloseApplications=force
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; first install: "launch now" checkbox on the last page
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; in-app update (runs silently): start the new version automatically
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent
