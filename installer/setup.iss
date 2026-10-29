; Inno Setup skripta za Etapa (https://jrsoftware.org/isinfo.php)
; Pravi se iz build.ps1 posle PyInstaller-a:  ISCC.exe /DAppVersion=1.1.0 installer\setup.iss
; Instalira se za trenutnog korisnika (bez administratorskih prava).

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{03B93763-4B56-40BE-B50C-7FC408EADF88}
AppName=Etapa
AppVersion={#AppVersion}
AppVerName=Etapa {#AppVersion}
AppPublisher=Etapa
DefaultDirName={localappdata}\Programs\Etapa
DefaultGroupName=Etapa
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Etapa-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Etapa.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Prečica na radnoj površini"; GroupDescription: "Dodatno:"

[Files]
Source: "..\dist\Etapa\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Etapa"; Filename: "{app}\Etapa.exe"
Name: "{group}\Deinstaliraj Etapa"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Etapa"; Filename: "{app}\Etapa.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Etapa.exe"; Description: "Pokreni Etapa"; Flags: nowait postinstall skipifsilent

; Podaci (%APPDATA%\Etapa: baza i kopije) se NE brišu pri deinstalaciji.
