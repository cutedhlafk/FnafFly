@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Brak srodowiska Python .venv. Zobacz README.md.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "src\autotrainer.py"

if errorlevel 1 pause
