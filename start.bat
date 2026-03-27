@echo off
cd /d "%~dp0"

set "PY="
python --version >nul 2>&1
if %errorlevel% equ 0 ( set "PY=python" & goto :start )
py --version >nul 2>&1
if %errorlevel% equ 0 ( set "PY=py" & goto :start )
for %%V in (313 312 311 310 39) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" & goto :start
    )
)
echo Python not found! & pause & exit /b 1

:start
set "PYW=%PY:python.exe=pythonw.exe%"
if exist "%PYW%" (
    start "" "%PYW%" price_alert_tracker.py
) else (
    powershell -WindowStyle Hidden -Command "Start-Process '%PY%' -ArgumentList 'price_alert_tracker.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
)
