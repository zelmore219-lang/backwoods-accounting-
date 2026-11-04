@echo off
cd /d "%~dp0..\.."
if not exist BUILD-APP-UPDATES-WINDOWS.cmd (
  echo Extract the complete repository ZIP and use its root build script.
  pause
  exit /b 1
)
call BUILD-APP-UPDATES-WINDOWS.cmd
