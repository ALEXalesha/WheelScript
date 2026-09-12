; Установщик WheelScript (Inno Setup 6). Собирается из build.ps1.

#define AppName "WheelScript"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\WheelScript"
#endif

[Setup]
AppId={{8C3E6F2A-4B1D-4E7A-9A51-6F0D2C7B3E19}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ALEXaloysha
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\release
OutputBaseFilename=WheelScript-{#AppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\WheelScript.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Ярлык в «Пуск» — по нему программа находится через поиск Windows.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\WheelScript.exe"; Comment: "Руль как мышь и клавиатура"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\WheelScript.exe"; Comment: "Руль как мышь и клавиатура"; Tasks: desktopicon

[Run]
Filename: "{app}\WheelScript.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
