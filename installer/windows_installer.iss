; Inno Setup Compiler Script for Argus PII Guard v1.0.5
; Builds a native Windows setup installer: Argus_PII_Guard_v1.0.5_Setup.exe

#define MyAppName "Argus PII Guard"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "Argus Security Team"
#define MyAppURL "https://github.com/argus-pii/argus-pii-guard"
#define MyAppExeName "Argus PII Guard.exe"
#define MyAppAppId "argus.piiguard.sentinel.1.0"

[Setup]
AppId={#MyAppAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installers
OutputBaseFilename=Argus_PII_Guard_v1.0.5_Setup
SetupIconFile=..\frontend\assets\argus-icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Argus PII Guard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\frontend\assets\argus-icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\frontend\assets\argus-icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; Register AppUserModelID for explicit Windows notifications & taskbar icon grouping
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\{#MyAppAppId}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
