#ifndef AppVersion
  #define AppVersion "1.3.0"
#endif
[Setup]
AppId={{6E3A405B-23D2-4B19-85B5-EE89B44FB902}
AppName=PaperFlow
AppVersion={#AppVersion}
AppPublisher=youges
AppPublisherURL=https://github.com/youges/paperflow
DefaultDirName={localappdata}\Programs\PaperFlow
DefaultGroupName=PaperFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=PaperFlow-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\assets\paperflow.ico
UninstallDisplayIcon={app}\PaperFlow.exe
LicenseFile=..\..\LICENSE.txt
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\..\dist\PaperFlow.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\PaperFlow-source.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{group}\PaperFlow"; Filename: "{app}\PaperFlow.exe"
Name: "{group}\Uninstall PaperFlow"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PaperFlow"; Filename: "{app}\PaperFlow.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\PaperFlow.exe"; Description: "Launch PaperFlow"; Flags: nowait postinstall skipifsilent
