@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" "src\download_data.py"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" "src\connectome.py"
if errorlevel 1 goto failed
echo Dane gotowe. Uruchom START_FLY.bat.
pause
exit /b 0
:failed
echo Przygotowanie danych nie powiodlo sie.
pause
exit /b 1
