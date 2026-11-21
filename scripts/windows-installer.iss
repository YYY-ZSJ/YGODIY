#ifndef ArchiveDir
  #define ArchiveDir SourcePath + "..\dist"
#endif
#ifndef InstalledBytes
  #error Supply /DInstalledBytes with the sum of the ZIP entries' uncompressed sizes.
#endif
#ifndef ArtBytes
  #error Supply /DArtBytes with the sum of the artwork entries' uncompressed sizes.
#endif
#ifndef ArtHash
  #error Supply /DArtHash with the SHA-256 of the artwork ZIP.
#endif
#define ProductVersion GetStringFileInfo(SourcePath + "..\dist\YGODIY\YGODIY.exe", "ProductVersion")
#define Bundle "YGODIY-" + ProductVersion + "-Windows-x64"
#define ArtArchive "YGODIY-" + ProductVersion + "-HD-Art.zip"
#define ArtURL "https://github.com/YYY-ZSJ/YGODIY/releases/download/v" + ProductVersion + "/" + ArtArchive
[Setup]
AppId=YGODIY.Desktop.{#ProductVersion}
AppName=YGODIY
AppVersion={#ProductVersion}
AppVerName=YGODIY {#ProductVersion}
AppPublisher=YGODIY
AppPublisherURL=https://github.com/YYY-ZSJ/YGODIY
DefaultDirName={userpf}\YGODIY
DefaultGroupName=YGODIY
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AllowNoIcons=yes
UninstallDisplayIcon={app}\{#Bundle}\YGODIY.exe
SetupIconFile=..\YGODIY.ico
OutputDir={#ArchiveDir}
OutputBaseFilename={#Bundle}-Setup
VersionInfoVersion={#ProductVersion}
VersionInfoProductVersion={#ProductVersion}
ArchiveExtraction=full
Compression=lzma2/fast

[Languages]
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#ArchiveDir}\{#Bundle}.zip"; DestDir: "{tmp}"; Flags: ignoreversion nocompression deleteafterinstall
Source: "{tmp}\{#Bundle}.zip"; DestDir: "{app}"; ExternalSize: {#InstalledBytes}; Flags: external extractarchive recursesubdirs createallsubdirs ignoreversion
Source: "{src}\{#ArtArchive}"; DestDir: "{app}\{#Bundle}"; ExternalSize: {#ArtBytes}; Hash: "{#ArtHash}"; Flags: external extractarchive recursesubdirs ignoreversion; Check: LocalArtwork
Source: "{#ArtURL}"; DestName: "{#ArtArchive}"; DestDir: "{app}\{#Bundle}"; ExternalSize: {#ArtBytes}; Hash: "{#ArtHash}"; Flags: external download extractarchive recursesubdirs ignoreversion; Check: not LocalArtwork

[Icons]
Name: "{group}\YGODIY {#ProductVersion}"; Filename: "{app}\{#Bundle}\YGODIY.exe"; WorkingDir: "{app}\{#Bundle}"
Name: "{autodesktop}\YGODIY {#ProductVersion}"; Filename: "{app}\{#Bundle}\YGODIY.exe"; WorkingDir: "{app}\{#Bundle}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#Bundle}\YGODIY.exe"; WorkingDir: "{app}\{#Bundle}"; Description: "{cm:LaunchProgram,YGODIY}"; Flags: postinstall nowait skipifsilent

[Code]
function LocalArtwork: Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\{#ArtArchive}'));
end;
