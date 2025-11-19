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
; *** MODIFICATION: Use the variable from the deploy.yml file ***
OutputBaseFilename={#SetupFilename}
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
; Source is the folder created by PyInstaller (assuming a 'one-dir' build)
Source: "dist\KaspaGateway\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Note: Ensure "dist\KaspaGateway" is the correct path from your PyInstaller output

[Tasks]
; --- Options during installation ---
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
; --- Start Menu and Desktop Icons ---
; Passes the user data path on startup.
;
; *** FIX ***
; IconFilename has been REMOVED. Inno Setup will now automatically
; extract the high-resolution icon embedded inside KaspaGateway.exe
; (which was set by the .spec file). This fixes the taskbar/desktop icon issue.
;
Name: "{group}\KaspaGateway"; Filename: "{app}\KaspaGateway.exe"; Parameters: "--user-data-path ""{userappdata}\KaspaGateway"""; WorkingDir: "{app}"
Name: "{userdesktop}\KaspaGateway"; Filename: "{app}\KaspaGateway.exe"; Parameters: "--user-data-path ""{userappdata}\KaspaGateway"""; WorkingDir: "{app}"; Tasks: desktopicon


[Registry]
; --- Add Autostart registry key (if user enables it in the app) ---
;
; This key is managed by the application's settings, but we ensure it's
; removed on uninstall.
; The app itself will create/delete this key based on user choice.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KaspaGateway"; ValueData: """{app}\KaspaGateway.exe"" --user-data-path ""{userappdata}\KaspaGateway"""; Flags: uninsdeletevalue createvalueifdoesntexist

[Run]
; --- Run application after install ---
Filename: "{app}\KaspaGateway.exe"; Parameters: "--user-data-path ""{userappdata}\KaspaGateway"""; Description: "{cm:LaunchProgram,KaspaGateway}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; --- Clean up user data on uninstall ---
; This ensures the database, logs, and config are removed.
Type: filesandordirs; Name: "{userappdata}\KaspaGateway"

; --- No [Code] section is needed for this simple installer ---