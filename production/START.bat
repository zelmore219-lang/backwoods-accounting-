@echo off
cd /d "%~dp0"
if exist "runtime\python.exe" (
  "runtime\python.exe" -E -s -B server.py
) else (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
  .venv\Scripts\python.exe server.py
)
pause
