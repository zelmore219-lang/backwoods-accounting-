@echo off
setlocal
cd /d "%~dp0"
if not exist "android-apps\main\android\gradlew.bat" goto incomplete
if not exist "android-apps\vendor\package-lock.json" goto incomplete
if not exist "android-apps\accounting\android\gradlew.bat" goto incomplete
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22 or later first.
  goto failed
)
if not defined ANDROID_HOME set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
if not exist "%ANDROID_HOME%\platforms\android-35\android.jar" (
  echo Open Android Studio - SDK Manager and install Android 15 API 35 and Build Tools 35.0.0.
  goto failed
)
if not defined JAVA_HOME if exist "%ProgramFiles%\Android\Android Studio\jbr\bin\javac.exe" set "JAVA_HOME=%ProgramFiles%\Android\Android Studio\jbr"
if not exist "%JAVA_HOME%\bin\javac.exe" (
  echo Install Android Studio with its Java 21 development kit, or set JAVA_HOME to a Java 21 JDK.
  goto failed
)

echo Installing pinned Android build dependencies...
call npm ci --prefix android-apps\main --no-audit --no-fund
if errorlevel 1 goto failed
call npm ci --prefix android-apps\vendor --no-audit --no-fund
if errorlevel 1 goto failed

pushd android-apps\main
call node_modules\.bin\cap.cmd sync android
if errorlevel 1 goto failedPop
pushd android
call gradlew.bat --no-daemon --max-workers=2 assembleDebug
if errorlevel 1 goto failedDoublePop
popd
popd
pushd android-apps\vendor
call node_modules\.bin\cap.cmd sync android
if errorlevel 1 goto failedPop
pushd android
call gradlew.bat --no-daemon --max-workers=2 assembleDebug
if errorlevel 1 goto failedDoublePop
popd
popd

pushd android-apps\accounting\android
call gradlew.bat --no-daemon --max-workers=2 testDebugUnitTest assembleDebug
if errorlevel 1 goto failedPop
popd

if not exist "android-apks" mkdir android-apks
copy /Y "android-apps\main\android\app\build\outputs\apk\debug\app-debug.apk" "android-apks\Backwoods-Brew-Connected-8.2.2-test.apk"
if errorlevel 1 goto failed
copy /Y "android-apps\vendor\android\app\build\outputs\apk\debug\app-debug.apk" "android-apks\Backwoods-Vendor-Connected-4.1.2-test.apk"
if errorlevel 1 goto failed
copy /Y "android-apps\accounting\android\app\build\outputs\apk\debug\app-debug.apk" "android-apks\Backwoods-Business-Accounting-1.0.1-test.apk"
if errorlevel 1 goto failed
echo All three installable test APKs are in android-apks.
echo Business Accounting requires your shared HTTPS company accounting server.
echo These use debug signing. Production releases need your own signing key.
explorer "%CD%\android-apks"
pause
exit /b 0

:failedDoublePop
popd
:failedPop
popd
goto failed
:incomplete
echo Extract the complete repository ZIP before building the APKs.
:failed
echo APK creation was not confirmed. Review the error above.
pause
exit /b 1
