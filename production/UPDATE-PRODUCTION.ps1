param([string]$TargetDirectory, [switch]$Quiet)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$source = Join-Path $PSScriptRoot 'application'
if (!(Test-Path (Join-Path $source 'server.py'))) { throw 'Extract the complete update ZIP before running this updater.' }
if (Get-Process -Name 'Backwoods Production' -ErrorAction SilentlyContinue) { throw 'Close Backwoods Production, including its notification icon, then run this update again.' }
if ($TargetDirectory) { $chosen = (Resolve-Path -LiteralPath $TargetDirectory).Path }
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
# Copy only application files; the database and existing executable/runtime stay in place.
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
if (!$Quiet) { [System.Windows.Forms.MessageBox]::Show("Production connection update installed. Original application files are in $backup. Open Production and choose Manager tools > Connections to connect your existing company.", 'Backwoods Production') | Out-Null }
