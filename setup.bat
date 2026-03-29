@echo off
title Preis-Alarm Tracker - Setup
color 0A
cls

echo.
echo  ============================================
echo    Preis-Alarm Tracker - Windows Setup
echo  ============================================
echo.

:: ── Python suchen (alle bekannten Installationspfade) ────────────────────────
set "PY="

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=python"
    goto :python_gefunden
)

for %%V in (313 312 311 310 39 38) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :python_gefunden
    )
    if exist "C:\Python%%V\python.exe" (
        set "PY=C:\Python%%V\python.exe"
        goto :python_gefunden
    )
    if exist "C:\Program Files\Python%%V\python.exe" (
        set "PY=C:\Program Files\Python%%V\python.exe"
        goto :python_gefunden
    )
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=py"
    goto :python_gefunden
)

:: Nicht gefunden → herunterladen
echo  [!] Python nicht gefunden. Wird jetzt heruntergeladen...
echo.
curl -L "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -o "%TEMP%\python_setup.exe" --progress-bar
if %errorlevel% neq 0 (
    echo  [X] Download fehlgeschlagen!
    echo  Bitte manuell installieren: https://www.python.org/downloads/
    echo  Wichtig: Haken bei "Add Python to PATH" setzen!
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
echo  Python wird installiert...
"%TEMP%\python_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
timeout /t 8 /nobreak >nul
for %%V in (311 312 313 310) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :python_gefunden
    )
)
echo  [X] Installation fehlgeschlagen. Bitte manuell installieren.
pause
exit /b 1

:python_gefunden
echo  [OK] Python: %PY%
echo.

:: ── pip + Bibliotheken ────────────────────────────────────────────────────────
echo  [i] pip wird geprueft...
"%PY%" -m pip --version >nul 2>&1
if %errorlevel% neq 0 ("%PY%" -m ensurepip --upgrade)
"%PY%" -m pip install --upgrade pip --quiet

echo  [i] Installiere Bibliotheken...
"%PY%" -m pip install requests beautifulsoup4 win10toast selenium webdriver-manager pystray pillow pyinstaller --quiet
if %errorlevel% neq 0 (
    echo  [X] Fehler bei der Installation!
    pause
    exit /b 1
)
echo  [OK] Fertig!
echo.

:: ── EXE bauen ─────────────────────────────────────────────────────────────────
echo  [i] Erstelle PreisAlarm.exe (1-2 Minuten)...
cd /d "%~dp0"
"%PY%" -m PyInstaller PreisAlarm.spec --clean

if %errorlevel% neq 0 (
    echo.
    echo  [!] EXE-Erstellung fehlgeschlagen - App laeuft trotzdem ueber start.bat
)

:: start.bat mit pythonw (kein CMD-Fenster)
set "PYW=%PY:python.exe=pythonw.exe%"
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo if exist "%PYW%" (
    echo     start "" "%PYW%" price_alert_tracker.py
    echo ) else (
    echo     powershell -WindowStyle Hidden -Command "Start-Process '%PY%' -ArgumentList 'price_alert_tracker.py' -WorkingDirectory '%%~dp0' -WindowStyle Hidden"
    echo )
) > starten_neu.bat
move /y starten_neu.bat start.bat >nul

if exist "dist\PreisAlarm.exe" (
    echo.
    echo  ============================================
    echo   [OK] dist\PreisAlarm.exe wurde erstellt!
    echo  ============================================
    powershell -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%USERPROFILE%\Desktop\Preis-Alarm Tracker.lnk'); $s.TargetPath='%~dp0dist\PreisAlarm.exe'; $s.Save()" >nul 2>&1
    echo  [OK] Desktop-Verknuepfung erstellt.
) else (
    echo.
    echo  [OK] start.bat wurde aktualisiert - bitte diese Datei verwenden.
)

echo.
echo  Druecke eine Taste zum Beenden...
pause >nul
