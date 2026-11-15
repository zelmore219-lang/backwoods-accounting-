param([Parameter(Mandatory=$true)][string]$TargetDirectory)
$ErrorActionPreference = 'Stop'
$env:PSModulePath = [IO.Path]::Combine($PSHOME,'Modules')
$payload = $PSScriptRoot
$target = [IO.Path]::GetFullPath($TargetDirectory).TrimEnd('\')
if ($target -eq [IO.Path]::GetPathRoot($target).TrimEnd('\')) { throw 'Choose an application folder, not the root of a drive.' }
$manifest = Get-Content -LiteralPath (Join-Path $payload 'PAYLOAD-MANIFEST.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
 $file = [IO.Path]::GetFullPath((Join-Path $payload $entry.Name))
 if (!$file.StartsWith($payload.TrimEnd('\')+'\', [StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $file -PathType Leaf) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw ('Installation file failed verification: '+$entry.Name) }
}
function Test-WebViewRuntime {
 foreach ($base in @($env:LOCALAPPDATA,${env:ProgramFiles(x86)},$env:ProgramFiles,$env:ProgramW6432)) {
  if (!$base) { continue }
  $folder = Join-Path $base 'Microsoft/EdgeWebView/Application'
  if (!(Test-Path -LiteralPath $folder)) { continue }
  foreach ($version in Get-ChildItem -LiteralPath $folder -Directory) {
   if (Test-Path -LiteralPath (Join-Path $version.FullName 'msedgewebview2.exe')) { return $true }
  }
 }
 return $false
}
if (!(Test-WebViewRuntime)) {
 $bootstrapper = Join-Path $payload 'MicrosoftEdgeWebView2Setup.exe'
 $signature = Get-AuthenticodeSignature -LiteralPath $bootstrapper
 if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') { throw 'Microsoft WebView2 setup failed its publisher signature check.' }
 $process = Start-Process -FilePath $bootstrapper -ArgumentList '/silent','/install' -Wait -PassThru
 if ($process.ExitCode -notin @(0,3010) -or !(Test-WebViewRuntime)) { throw 'Microsoft WebView2 Runtime could not be installed. Connect to the internet and run Setup again.' }
}
$currentSession = [Diagnostics.Process]::GetCurrentProcess().SessionId
if (Get-Process -Name 'Backwoods Production' -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $currentSession }) { throw 'Close Backwoods Production, including its notification icon, before installing.' }
$source = Join-Path $payload 'Application'
$files = @($manifest.PSObject.Properties | Where-Object { $_.Name.StartsWith('Application/',[StringComparison]::Ordinal) })
if (!$files.Count) { throw 'The complete Production application payload is required.' }
$homeDirectory = Join-Path $env:LOCALAPPDATA 'Backwoods Production'
$dataDirectory = Join-Path $homeDirectory 'Data'
$database = Join-Path $dataDirectory 'backwoods.db'
$legacyDatabases = @(@((Join-Path $target 'app/backwoods.db'),(Join-Path $target 'backwoods.db')) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
if (!(Test-Path -LiteralPath $database) -and $legacyDatabases.Count -gt 1) { throw 'More than one old Production database was found. Choose the authoritative database before installing; the existing files have not been changed.' }
$backup = $null
$saved = @{}
$copied = New-Object 'System.Collections.Generic.List[string]'
try {
 if (Test-Path -LiteralPath $target) {
  $backup = Join-Path (Split-Path $target -Parent) ('Production-installer-backup-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
  New-Item -ItemType Directory -Path $backup | Out-Null
 }
 foreach ($entry in $files) {
  $relative = $entry.Name.Substring('Application/'.Length)
  $destination = Join-Path $target $relative
  if ($relative -in @('app/index.html','app/sw.js','app/manifest.json','app/icon.svg') -and (Test-Path -LiteralPath $destination)) { continue }
  if (Test-Path -LiteralPath $destination) {
   $old = Join-Path $backup $relative
   New-Item -ItemType Directory -Force -Path (Split-Path $old -Parent) | Out-Null
   Copy-Item -LiteralPath $destination -Destination $old
   $saved[$destination]=$old
  }
  New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
  $copied.Add($destination)
  Copy-Item -LiteralPath (Join-Path $source $relative) -Destination $destination -Force
 }
 # The desktop launcher uses this same per-user data directory in every version.
 # When importing an older source/portable install, SQLite's backup API includes
 # committed WAL data. The source remains untouched; an existing desktop DB wins.
 if (!(Test-Path -LiteralPath $database) -and $legacyDatabases.Count -eq 1) {
  New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
  $temporary = Join-Path $dataDirectory ('production-migration-'+[guid]::NewGuid().ToString('N')+'.tmp')
  $script = 'import sqlite3,sys,pathlib; source=sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri()+''?mode=ro'',uri=True); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()'
  try {
   & (Join-Path $source 'runtime/python.exe') -E -s -B -c $script $legacyDatabases[0] $temporary
   if ($LASTEXITCODE -ne 0) { throw 'The old Production database could not be copied safely; its original file is unchanged.' }
   Move-Item -LiteralPath $temporary -Destination $database
  } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
 }
 $metadata = @{ version='1.0.0'; installedAt=(Get-Date).ToUniversalTime().ToString('o'); dataDirectory=$dataDirectory; applicationBackup=$backup }
 $metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target 'production-installation.json') -Encoding UTF8
 Write-Output 'Backwoods Production installed. Existing records and screen shell are preserved.'
} catch {
 foreach ($destination in $copied) {
  if ($saved.ContainsKey($destination)) { Copy-Item -LiteralPath $saved[$destination] -Destination $destination -Force }
  elseif (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Force }
 }
 throw
}
