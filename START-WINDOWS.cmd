@echo off
cd /d "%~dp0"
py -3 run.py
if errorlevel 1 (
  echo Start failed. Install Python 3.12 or later from python.org if Python is missing.
  pause
)
