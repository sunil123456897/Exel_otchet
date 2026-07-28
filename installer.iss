; Master-Report — Inno Setup installer for the compiled EXE distribution.
;
; Wraps the portable Nuitka build (build_exe\main.dist) into a setup.exe:
;   * installs the program into a user-writable folder ({localappdata}),
;     because the app writes its data (config/cache/logs) NEXT TO main.exe —
;     a read-only location like Program Files would break it for non-admins;
;   * creates Desktop + Start Menu shortcuts (launch + update);
;   * PRESERVES existing user data on upgrade (config/employees/cache are
;     excluded from the installed file set, so they are never overwritten);
;   * closes a running main.exe before installing so files are not locked.
;
; Build: tools\build_installer.bat  (needs Inno Setup 6 — ISCC.exe).
; The version is injected by the bat via /DMyAppVersion=<ver>.

#ifndef MyAppVersion
  #define MyAppVersion "5.6"
#endif
#define MyAppName "Master-Report"
#define MyAppPublisher "Master-Report"
#define SourceRoot "build_exe\main.dist"

[Setup]
AppId={{7B4F2A9E-5C63-4D8A-9E10-3F8B2C1D4E56}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Per-user install, no admin required (the app writes data beside the exe).
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=Master-Report_{#MyAppVersion}_Setup
SetupIconFile={#SourceRoot}\assets\icons\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
; Do not offer a "restart the computer" prompt.
AlwaysRestart=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
; The whole program tree. User DATA is excluded so an upgrade never clobbers
; an existing install's settings/cache (a fresh build's main.dist has none of
; these anyway — they are created at first run).
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
  Excludes: "config.yaml,employees.yaml,cache.db,cache.db-*,runtime_state.json,first_run.json,.license,.last_run,startup_log.txt,gui_error_log.txt,version.json,updater_exe_pin.txt,.update_*,logs,output,*.pyc"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\main.exe"; WorkingDir: "{app}"
Name: "{group}\Обновить {#MyAppName}"; Filename: "{app}\ОБНОВИТЬ_EXE.bat"; WorkingDir: "{app}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\main.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\main.exe"; Description: "Запустить {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
// Best-effort: close a running instance before install so program files are
// not locked. Failure is non-fatal (the user may simply not be running it).
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/F /IM main.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill', '/F /IM updater.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
