@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0UPDATE-PRODUCTION.ps1"
if errorlevel 1 pause
