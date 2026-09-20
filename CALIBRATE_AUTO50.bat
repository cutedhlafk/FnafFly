@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Brak srodowiska Python .venv.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "src\calibrate_auto50.py"

if errorlevel 1 pause