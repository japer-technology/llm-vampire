; Inno Setup wrapper for a PyInstaller onedir build.

#define AppName "LM Studio Vampire"
#define AppVersion "0.0.1"
#define AppPublisher "japer-technology"
#define AppExeName "LMStudioVampire.exe"

[Setup]
AppId={{LMStudioVampire}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\LM Studio Vampire
DefaultGroupName={#AppName}
OutputBaseFilename=LMStudioVampireSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\..\dist\LMStudioVampire\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"
