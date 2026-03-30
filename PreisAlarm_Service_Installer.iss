#define MyAppName      "Preis-Alarm Tracker Service"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "erdem-basar"
#define MyAppURL       "https://github.com/erdem-basar/price-alert-tracker"
#define MyServiceExe   "PreisAlarmService.exe"
#define MyAppIcon      "icon.ico"

[Setup]
AppId={{B1C3D5E7-9F2A-4B6C-8D0E-2F4A6B8C0D2E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={commonpf64}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=PreisAlarm_Service_Setup_{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\{#MyServiceExe}"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Service installieren und starten
Filename: "{app}\{#MyServiceExe}"; Parameters: "install"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Installiere Service..."
Filename: "{app}\{#MyServiceExe}"; Parameters: "start"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Starte Service..."

[UninstallRun]
; Service stoppen und entfernen
Filename: "{app}\{#MyServiceExe}"; Parameters: "stop";   Flags: runhidden; RunOnceId: "StopSvc"
Filename: "{app}\{#MyServiceExe}"; Parameters: "remove"; Flags: runhidden; RunOnceId: "RemoveSvc"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
