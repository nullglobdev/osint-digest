#ifndef AppVersion
#define AppVersion "1.2.0"
#endif
#ifndef AppSourceDir
#define AppSourceDir "../../dist/" + AppVersion + "/OSINTDigest"
#endif
[Setup]
AppId={{B212567B-9F98-4F42-AC83-31B1EAC7F670}
AppName=OSINT Digest
AppVersion={#AppVersion}
AppPublisher=OSINT Digest
DefaultDirName={localappdata}\Programs\OSINT Digest
DefaultGroupName=OSINT Digest
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=OSINTDigest-Setup-{#AppVersion}-x64
SetupIconFile=..\..\assets\app.ico
UninstallDisplayIcon={app}\OSINTDigest.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
InfoBeforeFile=install-notes.txt

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OSINT Digest"; Filename: "{app}\OSINTDigest.exe"
Name: "{autodesktop}\OSINT Digest"; Filename: "{app}\OSINTDigest.exe"; Tasks: desktopicon
Name: "{group}\Uninstall OSINT Digest"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\OSINTDigest.exe"; Description: "Open OSINT Digest"; Flags: nowait postinstall skipifsilent
