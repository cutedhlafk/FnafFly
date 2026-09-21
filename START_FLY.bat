@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Brak srodowiska Python .venv. Zobacz README.md.
  pause
  exit /b 1
)

if not exist "audio_capture\bin\publish\AudioCapture.exe" powershell -NoProfile -ExecutionPolicy Bypass -File "build_audio.ps1"
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_fly.ps1"

if errorlevel 1 pause
