@echo off
setlocal
cd /d "%~dp0"

if not exist "source-app-updates\main\electron\connected-profile.cjs" goto incomplete
if not exist "source-app-updates\vendor\electron\desktop-feed.cjs" goto incomplete
if not exist "desktop\package-lock.json" goto incomplete
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22 or later from https://nodejs.org/ first.
  goto failed
)
node -e "if(Number(process.versions.node.split('.')[0])<22)process.exit(1)"
if errorlevel 1 goto failed

echo Installing the pinned Windows packaging tools...
call npm ci --prefix desktop --ignore-scripts --no-audit --no-fund
if errorlevel 1 goto failed
if defined HTTPS_PROXY (
  set "ELECTRON_GET_USE_PROXY=1"
  set "GLOBAL_AGENT_HTTPS_PROXY=%HTTPS_PROXY%"
)
if defined HTTP_PROXY set "GLOBAL_AGENT_HTTP_PROXY=%HTTP_PROXY%"

echo Checking source-app scripts...
node --check source-app-updates\main\electron\main.cjs
if errorlevel 1 goto failed
node --check source-app-updates\main\electron\connected-profile.cjs
if errorlevel 1 goto failed
node --check source-app-updates\vendor\electron\main.cjs
if errorlevel 1 goto failed
node --check source-app-updates\vendor\electron\desktop-feed.cjs
if errorlevel 1 goto failed
node source-app-updates\main\scripts\verify.cjs
if errorlevel 1 goto failed
node tests\source_updates.test.cjs
if errorlevel 1 goto failed

echo Building the Backwoods Brew Connected installer...
call desktop\node_modules\.bin\electron-builder.cmd --projectDir source-app-updates\main --win nsis --x64 --publish never
if errorlevel 1 goto failed
echo Building the Vendor Ordering Connected installer...
call desktop\node_modules\.bin\electron-builder.cmd --projectDir source-app-updates\vendor --win nsis --x64 --publish never
if errorlevel 1 goto failed

echo.
echo Both connected-app installers were built in dist\source-app-updates.
echo Back up both source apps and close them before the first connected launch.
echo Use a separate Windows user for a fully isolated test of all three apps.
explorer "%CD%\dist\source-app-updates"
pause
exit /b 0

:incomplete
echo Extract the complete repository ZIP before running this script.
echo The source-app-updates and desktop folders must be beside this file.
:failed
echo The update installers were not confirmed as built. See the error above.
pause
exit /b 1
