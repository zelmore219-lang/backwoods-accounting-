param([string]$TargetDirectory, [switch]$Quiet)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$source = Join-Path $PSScriptRoot 'application'
if (!(Test-Path (Join-Path $source 'server.py'))) { throw 'Extract the complete update ZIP before running this updater.' }
if (Get-Process -Name 'Backwoods Production' -ErrorAction SilentlyContinue) { throw 'Close Backwoods Production, including its notification icon, then run this update again.' }
if ($TargetDirectory) { $chosen = (Resolve-Path -LiteralPath $TargetDirectory).Path }
elseif (Test-Path (Join-Path $env:LOCALAPPDATA 'Backwoods Production/Application/Backwoods Production.exe')) { $chosen = Join-Path $env:LOCALAPPDATA 'Backwoods Production/Application' }
else {
 $picker = New-Object System.Windows.Forms.FolderBrowserDialog
 $picker.Description = 'Select the existing Backwoods Production Application folder (the folder containing Backwoods Production.exe).'
 $picker.ShowNewFolderButton = $false
 if ($picker.ShowDialog() -ne 'OK') { exit 0 }
 $chosen = $picker.SelectedPath
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'SHA256-MANIFEST.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
 $file = Join-Path $PSScriptRoot $entry.Name
 if (!(Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw ('Update file failed verification: ' + $entry.Name) }
}
if (!(Test-Path (Join-Path $chosen 'Backwoods Production.exe'))) { throw 'That folder does not contain the existing Backwoods Production executable. No files were changed.' }
$candidates = @(Get-ChildItem -LiteralPath $chosen -Filter server.py -File -Recurse | Where-Object { Test-Path (Join-Path $_.DirectoryName 'operations.py') })
if ($candidates.Count -ne 1) { throw 'Exactly one existing Production server.py must be present. No files were changed.' }
$target = $candidates[0].DirectoryName
$backup = Join-Path (Split-Path $chosen -Parent) ('Production-update-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($file in Get-ChildItem -LiteralPath $source -File) {
 $old = Join-Path $target $file.Name
 if (Test-Path $old) { Copy-Item -LiteralPath $old -Destination $backup }
}
if (Test-Path (Join-Path $target 'vendor')) { Copy-Item -LiteralPath (Join-Path $target 'vendor') -Destination $backup -Recurse }
# Keep the existing screen shell, styles, icon and PWA files byte-for-byte.
# app.js only adds background status and excludes packages assigned to Vendor.
foreach ($entry in Get-ChildItem -LiteralPath $source) {
 if ($entry.Name -in @('index.html','sw.js','manifest.json','icon.svg')) { continue }
 Copy-Item -LiteralPath $entry.FullName -Destination $target -Recurse -Force
}
if (!$Quiet) { [System.Windows.Forms.MessageBox]::Show("Production background connection installed. Your existing Production screens and production tasks are retained. Original application files are in $backup. Reopen Production, then run CONNECT-EXISTING-APPS.cmd from this extracted folder for one-time company setup.", 'Backwoods Production') | Out-Null }
