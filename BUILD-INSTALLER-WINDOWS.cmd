@echo off
setlocal
cd /d "%~dp0"

rem Opening this CMD inside a ZIP extracts only the selected file into Temp.
rem Require the full project before downloading or installing build tools.
if not exist "desktop\package.json" goto incompleteFolder
if not exist "desktop\package-lock.json" goto incompleteFolder
if not exist "desktop\electron-builder.yml" goto incompleteFolder
if not exist "accounting\server.py" goto incompleteFolder
if not exist "web\index.html" goto incompleteFolder

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
echo Copying the portable runtime into the installer folder...
if not exist ".build-resources\python" mkdir ".build-resources\python"
if not exist ".build-resources\python" (
  echo Could not create the runtime destination. Move the extracted app to a short local path, such as C:\BackwoodsBuild.
  goto failed
)
rem Robocopy supports long Windows paths. Exit codes 0 through 7 are successful.
rem Do not use /MIR: preserve any other existing build files.
robocopy ".build-resources\managed-python\cpython-3.12.15-windows-x86_64-none" ".build-resources\python" /E /R:1 /W:1 /NFL /NDL /NP
if errorlevel 8 goto failed
if not exist ".build-resources\python\python.exe" (
  echo The runtime copy did not produce python.exe. See the copy results above.
  goto failed
)

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

:incompleteFolder
echo.
echo The complete app folder was not found beside this build script.
echo Do not run this file from inside the downloaded ZIP.
echo Right-click the ZIP, choose Extract All, then open the extracted folder.
echo It must contain the desktop, accounting, scripts, and web folders.
echo Double-click BUILD-INSTALLER-WINDOWS.cmd from that extracted folder.
goto failed

:failed
echo.
echo The installer was not confirmed as built. Read the error above.
pause
exit /b 1
