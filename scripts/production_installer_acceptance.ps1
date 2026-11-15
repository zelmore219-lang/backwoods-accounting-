$ErrorActionPreference = 'Stop'
$output = Join-Path (Get-Location) 'dist/production-installer'
$installer = Join-Path $output 'Backwoods-Production-Setup-1.0.1.exe'
$homeDirectory = Join-Path $env:LOCALAPPDATA 'Backwoods Production'
$app = Join-Path $homeDirectory 'Application'
$dataDirectory = Join-Path $homeDirectory 'Data'
$database = Join-Path $dataDirectory 'backwoods.db'
$stage = Join-Path $env:RUNNER_TEMP 'production-installer-acceptance'
$payloadPython = Join-Path $output 'payload/Application/runtime/python.exe'
if (Test-Path -LiteralPath $homeDirectory) { throw 'Use a disposable Windows runner without existing Production records.' }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$liveProcess=$null; $walProcess=$null
function Run-Setup([int]$ExpectedExit=0) {
 $process=Start-Process -FilePath $installer -ArgumentList '/S' -Wait -PassThru
 if ($process.ExitCode -ne $ExpectedExit) { throw ('Production Setup exit code '+$process.ExitCode+'; expected '+$ExpectedExit) }
}
function Run-Window {
 $process=Start-Process -FilePath (Join-Path $app 'Backwoods Production.exe') -ArgumentList @('--smoke-test',('"'+$database+'"')) -PassThru
 if (!$process.WaitForExit(120000)) { $process.Kill(); throw 'The installed Production window timed out.' }
 if ($process.ExitCode -ne 0) { throw 'The installed original Production window failed its native render check.' }
}
function Check-Records([switch]$Migrated) {
 # Bind IDs as parameters rather than relying on native-command quote handling.
 $code="import sqlite3,sys,pathlib,json; db=sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri()+'?mode=ro',uri=True); assert json.loads(db.execute('select data from records where id=?',('installer-preserved',)).fetchone()[0])['quantity']==7; assert db.execute('pragma quick_check').fetchone()[0]=='ok'; assert not int(sys.argv[2]) or db.execute('select count(*) from records where id=?',('wal-migrated',)).fetchone()[0]==1; db.close()"
 & $payloadPython -E -s -B -c $code $database ([int]$Migrated.IsPresent)
 if ($LASTEXITCODE -ne 0) { throw 'An installed Production record was lost or corrupted.' }
}
function Stop-TestDesktop {
 if ($liveProcess -and !$liveProcess.HasExited) {
  Get-CimInstance Win32_Process -Filter ('ParentProcessId = '+$liveProcess.Id) | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Stop-Process -Id $liveProcess.Id -Force -ErrorAction SilentlyContinue
  $liveProcess.WaitForExit(10000) | Out-Null
 }
}
try {
 # The setup must fail before writing anything when its extracted payload differs.
 $bad=Join-Path $stage 'bad-payload';Copy-Item -LiteralPath (Join-Path $output 'payload') -Destination $bad -Recurse
 Add-Content -LiteralPath (Join-Path $bad 'Application/app/server.py') -Value '# changed fixture'
 $badTarget=Join-Path $stage 'must-not-install'
 $arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+(Join-Path $bad 'Install-Production.ps1')+'" -TargetDirectory "'+$badTarget+'"'
 $process=Start-Process powershell.exe -ArgumentList $arguments -Wait -PassThru -RedirectStandardError (Join-Path $stage 'expected-integrity-error.txt')
 if ($process.ExitCode -eq 0 -or (Test-Path -LiteralPath $badTarget)) { throw 'A modified installer payload was accepted.' }
 Run-Setup
 foreach ($name in @('Backwoods Production.exe','runtime/python.exe','app/server.py','app/vendor/cryptography/__init__.py','CONNECT-EXISTING-APPS.cmd','Uninstall.exe')) {
  if (!(Test-Path -LiteralPath (Join-Path $app $name))) { throw ('Missing installed file: '+$name) }
 }
 $registration=Get-ItemProperty 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/BackwoodsProduction'
 if ($registration.DisplayVersion -ne '1.0.1' -or $registration.InstallLocation -ne $app) { throw 'Windows app registration is incomplete.' }
 $shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Backwoods Production.lnk'))
 if ($shortcut.TargetPath -ne (Join-Path $app 'Backwoods Production.exe')) { throw 'The desktop shortcut does not launch the original Production app.' }
 # Exercise normal launch, not just the test switch, and reject replacing a live app.
 $liveProcess=Start-Process -FilePath $shortcut.TargetPath -PassThru
 $deadline=(Get-Date).AddSeconds(60);$ready=$false
 do {
  if ($liveProcess.HasExited) { throw 'The newly installed Production desktop exited during startup.' }
  try { $state=Invoke-RestMethod 'http://127.0.0.1:8765/api/me' -TimeoutSec 2; $ready=($null -ne $state.setup) } catch {}
  if (!$ready) { Start-Sleep -Milliseconds 250 }
 } until ($ready -or (Get-Date) -gt $deadline)
 if (!$ready -or !(Test-Path -LiteralPath $database)) { throw 'Normal launch did not start Production and its retained data directory.' }
 $setupError=Join-Path $stage 'expected-setup-before-manager.txt'
 $arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+(Join-Path $app 'CONNECT-EXISTING-APPS.ps1')+'"'
 $process=Start-Process powershell.exe -ArgumentList $arguments -Wait -PassThru -RedirectStandardError $setupError
 if ($process.ExitCode -eq 0 -or (Get-Content -LiteralPath $setupError -Raw) -notmatch 'Create your original manager account') { throw 'Connection setup did not identify the installed Production desktop server before requesting credentials.' }
 $before=(Get-FileHash -LiteralPath (Join-Path $app 'app/server.py') -Algorithm SHA256).Hash
 Run-Setup 10
 if ((Get-FileHash -LiteralPath (Join-Path $app 'app/server.py') -Algorithm SHA256).Hash -ne $before) { throw 'Setup changed an application that was running.' }
 Stop-TestDesktop
 Run-Window
 $env:BACKWOODS_DB_PATH=$database
 Push-Location (Join-Path $app 'app')
 try {
  & (Join-Path $app 'runtime/python.exe') -E -s -B -c "import server,json; c=server.connect(); c.execute('INSERT INTO records VALUES(?,?,?)',('installer-preserved','materials',json.dumps({'name':'Disposable installer fixture','quantity':7,'cost':2,'unit':'lb'}))); c.commit(); c.close(); import cryptography; from cryptography.hazmat.primitives.ciphers.aead import AESGCM; AESGCM.generate_key(256)"
  if ($LASTEXITCODE -ne 0) { throw 'The bundled Python or native cryptography did not work.' }
 } finally { Pop-Location }
 # Recreate the supplied unmanaged app in the same installation, then upgrade it.
 Expand-Archive tests/fixtures/production-desktop/original-application.zip (Join-Path $app 'app') -Force
 [IO.File]::AppendAllText((Join-Path $app 'app/index.html'),'<!-- preserved legacy screen fixture -->')
 [IO.File]::WriteAllText((Join-Path $app 'customer-notes.txt'),'Unrelated file retained by uninstall')
 Copy-Item -LiteralPath $database -Destination (Join-Path $app 'app/backwoods.db')
 Remove-Item 'HKCU:/Software/BackwoodsProduction' -Recurse
 Remove-Item 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/BackwoodsProduction' -Recurse
 $databaseHash=(Get-FileHash -LiteralPath $database -Algorithm SHA256).Hash
 $screenHashes=@{}
 foreach ($name in @('index.html','sw.js','manifest.json','icon.svg')) { $screenHashes[$name]=(Get-FileHash -LiteralPath (Join-Path $app ('app/'+$name)) -Algorithm SHA256).Hash }
 foreach ($pass in @(1,2)) {
  Run-Setup
  if ((Get-FileHash -LiteralPath $database -Algorithm SHA256).Hash -ne $databaseHash) { throw 'Installing or reinstalling changed the existing database bytes.' }
  foreach ($name in $screenHashes.Keys) { if ((Get-FileHash -LiteralPath (Join-Path $app ('app/'+$name)) -Algorithm SHA256).Hash -ne $screenHashes[$name]) { throw 'An original Production screen asset was replaced.' } }
  Check-Records
  Run-Window
 }
 $backups=@(Get-ChildItem -LiteralPath $homeDirectory -Directory | Where-Object { $_.Name -like 'Production-installer-backup-*' })
 if ($backups.Count -lt 2) { throw 'Application upgrade backups are missing.' }
 $process=Start-Process -FilePath (Join-Path $app 'Uninstall.exe') -ArgumentList '/S' -Wait -PassThru
 if ($process.ExitCode -ne 0) { throw 'Production uninstall failed.' }
 if ((Test-Path -LiteralPath (Join-Path $app 'Backwoods Production.exe')) -or !(Test-Path -LiteralPath (Join-Path $app 'customer-notes.txt')) -or !(Test-Path -LiteralPath (Join-Path $app 'app/backwoods.db'))) { throw 'Uninstall removed unrelated data or did not remove the program.' }
 Check-Records
 # A portable/source database with committed, uncheckpointed WAL records migrates
 # only when the normal desktop database is absent. Preserve both originals.
 Move-Item -LiteralPath $dataDirectory -Destination (Join-Path $stage 'retained-desktop-data')
 $legacyDatabase=Join-Path $app 'app/backwoods.db';$readyFile=Join-Path $stage 'wal-ready';$stopFile=Join-Path $stage 'wal-stop'
 $writer=Join-Path $stage 'wal-writer.py'
 @'
import json,pathlib,sqlite3,sys,time
database,ready,stop=map(pathlib.Path,sys.argv[1:])
c=sqlite3.connect(database);c.execute('PRAGMA journal_mode=WAL')
c.execute('INSERT INTO records VALUES(?,?,?)',('wal-migrated','materials',json.dumps({'name':'WAL migration fixture','quantity':11,'cost':1,'unit':'lb'})));c.commit()
ready.write_text('ready')
for attempt in range(600):
 if stop.exists():break
 time.sleep(.1)
c.close()
'@ | Set-Content -LiteralPath $writer -Encoding UTF8
 $arguments='-E -s -B "'+$writer+'" "'+$legacyDatabase+'" "'+$readyFile+'" "'+$stopFile+'"'
 $walProcess=Start-Process -FilePath $payloadPython -ArgumentList $arguments -PassThru
 $deadline=(Get-Date).AddSeconds(20)
 while (!(Test-Path -LiteralPath $readyFile) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
 if (!(Test-Path -LiteralPath $readyFile) -or !(Test-Path -LiteralPath ($legacyDatabase+'-wal'))) { throw 'The portable WAL migration fixture did not start.' }
 Run-Setup
 Check-Records -Migrated
 [IO.File]::WriteAllText($stopFile,'stop');$walProcess.WaitForExit(10000) | Out-Null
 if (!(Test-Path -LiteralPath $legacyDatabase) -or !(Test-Path -LiteralPath (Join-Path $stage 'retained-desktop-data/backwoods.db'))) { throw 'Migration removed an original database.' }
 Run-Window
 @{ sourceCommit=$env:GITHUB_SHA; version='1.0.1'; freshInstall=$true; originalDesktopLaunch=$true; nativeWebViewRender=$true; originalLauncherAndScreenAssetsPreserved=$true; installedConnectionOriginDetected=$true; legacyUpgrade=$true; reinstall=$true; applicationBackups=$true; existingDatabaseBytesPreserved=$true; nativePythonAndCryptography=$true; runningAppReplacementBlocked=$true; modifiedPayloadRejected=$true; uninstallPreservesRecordsAndUnrelatedFiles=$true; portableWalDatabaseMigratedWithoutDeletingOriginal=$true; otherAppFeedsChanged=$false } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'INSTALLER-ACCEPTANCE.json')
} catch {
 $_ | Out-String | Set-Content -LiteralPath (Join-Path $output 'INSTALLER-ERROR.txt')
 if (Test-Path -LiteralPath (Join-Path $env:TEMP 'Backwoods-Production-Setup-error.txt')) { Get-Content -LiteralPath (Join-Path $env:TEMP 'Backwoods-Production-Setup-error.txt') | Add-Content -LiteralPath (Join-Path $output 'INSTALLER-ERROR.txt') }
 if (Test-Path -LiteralPath (Join-Path $app 'verification-error.txt')) { Copy-Item -LiteralPath (Join-Path $app 'verification-error.txt') -Destination $output }
 throw
} finally {
 Stop-TestDesktop
 if ($walProcess -and !$walProcess.HasExited) { Stop-Process -Id $walProcess.Id -Force -ErrorAction SilentlyContinue }
}
