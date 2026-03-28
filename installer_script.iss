; Inno Setup Script for KaspaGateway
;
; This script defines how the Windows installer is built, including
; file locations, registry keys, and shortcuts.

[Setup]
; --- Basic Application Info ---
AppName=KaspaGateway
AppVersion=1.0.0
; --- Unique App ID for version tracking and uninstallation ---
AppID={{5A1E1E6B-0B8E-4A4A-8A8C-3C6D4A5B7B1F}}
AppPublisher=KaspaPulse
DefaultDirName={autopf64}\KaspaGateway
DefaultGroupName=KaspaGateway
AllowNoIcons=yes
LicenseFile=LICENSE

; --- Standard Update Handling ---
; If a previous version is installed, the new installer will simply overwrite it.
; The AppID ensures the old version's registry entry is found and overwritten.
UsePreviousAppDir=yes

; --- Installation Privileges ---
; Run as user (non-admin) since we are writing to HKCU and userappdata
PrivilegesRequired=lowest

; --- Output Installer File ---
OutputDir=dist
; *** FIXED: Using static name for local build instead of undeclared variable ***
OutputBaseFilename=KaspaGateway_v1.0.0_Setup
SetupIconFile=assets\kaspa-white.ico
; *** FIX: Added this line to show the icon in 'Add or Remove Programs' ***
UninstallDisplayIcon={app}\KaspaGateway.exe
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ar"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Dirs]
; --- Create User Data Directory ---
; This ensures user data (DBs, logs) is stored correctly in %APPDATA%
Name: "{userappdata}\KaspaGateway"; Flags: uninsneveruninstall

[Files]
; --- Files to Install ---
; Source is the folder created by PyInstaller
Source: "dist\KaspaGateway\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
; --- Options during installation ---
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
; --- Start Menu and Desktop Icons ---
; *** FIX ***
; IconFilename has been REMOVED. Inno Setup will now automatically
; extract the high-resolution icon embedded inside KaspaGateway.exe
Name: "{group}\KaspaGateway"; Filename: "{app}\KaspaGateway.exe"; Parameters: "--user-data-path ""{userappdata}\KaspaGateway"""; WorkingDir: "{app}"
Name: "{userdesktop}\KaspaGateway"; Filename: "{app}\KaspaGateway.exe"; Parameters: "--user-data-path ""{userappdata}\KaspaGateway"""; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; --- Add Autostart registry key ---
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KaspaGateway"; ValueData: """{app}\KaspaGateway.exe"" --user-data-path ""{userappdata}\KaspaGateway"""; Flags: uninsdeletevalue createvalueifdoesntexist

[Run]
; --- Run application after install ---
Filename: "{app}\KaspaGateway.exe"; Parameters: "--user-data-path ""{userappdata}\KaspaGateway"""; Description: "{cm:LaunchProgram,KaspaGateway}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; --- Clean up user data on uninstall ---
Type: filesandordirs; Name: "{userappdata}\KaspaGateway"