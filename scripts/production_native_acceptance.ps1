$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$stage = Join-Path $env:RUNNER_TEMP 'production-connection-native'
$app = Join-Path $env:LOCALAPPDATA 'Backwoods Production/Application'
$data = Join-Path $env:LOCALAPPDATA 'Backwoods Production/Data'
if (Test-Path (Join-Path $data 'backwoods.db')) { throw 'A disposable Windows runner is required; existing Production records were found.' }
New-Item -ItemType Directory -Force $stage, $app, $data | Out-Null
Copy-Item tests/fixtures/production-desktop/*.exe $app
Copy-Item tests/fixtures/production-desktop/*.dll $app
Expand-Archive tests/fixtures/production-desktop/original-application.zip (Join-Path $app 'app')
$runtimeZip = Join-Path $stage 'python-3.14.0.zip'
Invoke-WebRequest 'https://www.python.org/ftp/python/3.14.0/python-3.14.0-embed-amd64.zip' -OutFile $runtimeZip
if ((Get-FileHash $runtimeZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne '8d4d3590c10449d78aa4375f534e6d5f3027d67fdc362dd1a882279db6f90fdf') { throw 'The retained Python runtime checksum differs.' }
Expand-Archive $runtimeZip (Join-Path $app 'runtime')
$runtime = Join-Path $app 'runtime'
$dlls = Join-Path $runtime 'DLLs'
New-Item -ItemType Directory -Force $dlls | Out-Null
Get-ChildItem $runtime -Filter '*.pyd' -File | Move-Item -Destination $dlls
Get-ChildItem $runtime -Filter '*.dll' -File | Where-Object { $_.Name -notmatch '^(python3|python314|vcruntime140|vcruntime140_1)\.dll$' } | Move-Item -Destination $dlls
Copy-Item tests/fixtures/production-desktop/python314._pth (Join-Path $runtime 'python314._pth')
$python = Join-Path $app 'runtime/python.exe'
$program = Join-Path $app 'app'
$env:BACKWOODS_DB_PATH = Join-Path $data 'backwoods.db'
Push-Location $program
try {
 & $python -E -s -B -c "import server,json;server.initialize();c=server.connect();c.execute('INSERT INTO records VALUES(?,?,?)',('native-preserved-material','materials',json.dumps({'name':'Native preservation fixture','quantity':7,'cost':2,'unit':'lb'})));c.commit();c.close()"
 if ($LASTEXITCODE -ne 0) { throw 'Original Production source could not initialize its retained database.' }
} finally { Pop-Location }
function Verify-Window {
 $process = Start-Process (Join-Path $app 'Backwoods Production.exe') -ArgumentList @('--smoke-test', ('"' + $env:BACKWOODS_DB_PATH + '"')) -PassThru
 if (!$process.WaitForExit(120000)) { $process.Kill(); throw 'The actual Production desktop verification timed out.' }
 if ($process.ExitCode -ne 0) { throw ('The actual Production desktop failed verification: ' + $process.ExitCode) }
}
Verify-Window
$update = Join-Path $stage 'update'
Expand-Archive dist/production/Backwoods-Production-Connected-Update.zip $update
foreach ($pass in @(1,2)) {
 & (Join-Path $update 'UPDATE-PRODUCTION.ps1') -Quiet
 if (!$?) { throw 'Production application update failed.' }
 Push-Location $program
 try {
  & $python -E -s -B -c "import sys;sys.path.insert(0,'vendor');import cryptography,finance,connected,sync,server;server.initialize();c=server.connect();assert c.execute('SELECT data FROM records WHERE id=?',('native-preserved-material',)).fetchone();assert sync.run(server.connect)['message'];print('retained Production database and native cryptography verified');c.close()"
  if ($LASTEXITCODE -ne 0) { throw 'The exact updated Python 3.14 application failed verification.' }
 } finally { Pop-Location }
 Verify-Window
}
@{ originalShellVerified=$true; updateAndReinstallVerified=$true; originalDatabasePreserved=$true; nativeCryptoVerified=$true; sourceCommit=$env:GITHUB_SHA } | ConvertTo-Json | Set-Content dist/production/WINDOWS-ACCEPTANCE.json
