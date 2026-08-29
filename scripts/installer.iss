#define MyAppName "PoseCare"
#define MyAppPublisher "PoseCare"
#define MyAppUrl "https://github.com/Yuubinkyokutyou/pose-care"
#define MyAppExeName "PoseCare.exe"
#define MyAppVersion GetEnv("POSE_CARE_INSTALLER_VERSION")
#define MySourceDir GetEnv("POSE_CARE_INSTALLER_SOURCE")
#define MyOutputDir GetEnv("POSE_CARE_INSTALLER_OUTPUT")

#if MyAppVersion == ""
  #error "POSE_CARE_INSTALLER_VERSION is required"
#endif
#if MySourceDir == ""
  #error "POSE_CARE_INSTALLER_SOURCE is required"
#endif
#if MyOutputDir == ""
  #error "POSE_CARE_INSTALLER_OUTPUT is required"
#endif

[Setup]
AppId={{B54A85C3-F275-4A40-99D7-FE43B958E87D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}/issues
AppUpdatesURL={#MyAppUrl}/releases/latest
DefaultDirName={localappdata}\Programs\PoseCare
DisableDirPage=yes
UsePreviousAppDir=no
DefaultGroupName=PoseCare
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyOutputDir}
OutputBaseFilename=PoseCareSetup-windows-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=PoseCare.exe
RestartApplications=no
SetupLogging=yes
Uninstallable=yes
UninstallFilesDir={localappdata}\PoseCare\uninstall
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=PoseCare Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; GroupDescription: "追加のショートカット:"; Flags: checkedonce

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PoseCare"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\PoseCare"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PoseCare"; ValueData: """{app}\{#MyAppExeName}"""; Check: ExistingStartupRegistration; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "PoseCare"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "PoseCareを起動する"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function ExistingStartupRegistration(): Boolean;
var
  ExistingValue: String;
begin
  Result := RegQueryStringValue(
    HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Run',
    'PoseCare',
    ExistingValue
  ) and (ExistingValue <> '');
end;
