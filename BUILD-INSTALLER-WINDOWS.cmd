@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22 or later from https://nodejs.org/ and run this again.
  goto failed
)
node -e "if(Number(process.versions.node.split('.')[0])<22)process.exit(1)"
if errorlevel 1 (
  echo Node.js 22 or later is required.
  goto failed
)
py -3 -c "import sys; raise SystemExit(sys.version_info[:2] < (3,12))" >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.12 or later from https://www.python.org/ with the Python launcher enabled.
  goto failed
)

echo Preparing isolated installer tools...
if not exist ".build-tools\Scripts\python.exe" py -3 -m venv .build-tools
if errorlevel 1 goto failed
set "BACKWOODS_BUILD_PY=%CD%\.build-tools\Scripts\python.exe"
"%BACKWOODS_BUILD_PY%" -m pip install --disable-pip-version-check "uv==0.13.4"
if errorlevel 1 goto failed

echo Downloading the verified, portable Windows runtime...
"%BACKWOODS_BUILD_PY%" -m uv python install --install-dir "%CD%\.build-resources\managed-python" --no-bin --no-registry cpython-3.12.15-windows-x86_64-none
if errorlevel 1 goto failed
if not exist ".build-resources\managed-python\cpython-3.12.15-windows-x86_64-none\python.exe" (
  echo The portable runtime was not found at the expected path.
  goto failed
)
xcopy ".build-resources\managed-python\cpython-3.12.15-windows-x86_64-none\*" ".build-resources\python\" /E /I /H /Y >nul
if errorlevel 1 goto failed

echo Installing the pinned desktop build dependencies...
call npm ci --prefix desktop --ignore-scripts --no-audit --no-fund
if errorlevel 1 goto failed

echo Checking the application...
"%BACKWOODS_BUILD_PY%" -m unittest discover -s tests -q
if errorlevel 1 goto failed

echo Building the Windows installer. This can take several minutes...
if defined HTTPS_PROXY (
  set "ELECTRON_GET_USE_PROXY=1"
  set "GLOBAL_AGENT_HTTPS_PROXY=%HTTPS_PROXY%"
)
if defined HTTP_PROXY set "GLOBAL_AGENT_HTTP_PROXY=%HTTP_PROXY%"
call desktop\node_modules\.bin\electron-builder.cmd --config desktop\electron-builder.yml --win nsis --x64 --publish never
if errorlevel 1 goto failed

echo.
echo Build complete. Your installer is in dist\windows\
echo Backwoods-Business-Accounting-Setup-1.0.0.exe
echo The installer includes its Python runtime. No payroll credentials are included.
explorer "%CD%\dist\windows"
pause
exit /b 0

:failed
echo.
echo The installer was not confirmed as built. Read the error above.
pause
exit /b 1
