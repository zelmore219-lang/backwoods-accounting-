param([string]$Origin = 'http://127.0.0.1:8080')
$ErrorActionPreference = 'Stop'
if ($Origin -notmatch '^http://(127\.0\.0\.1|localhost):[0-9]+$') { throw 'Connection setup only accepts the local Production server.' }
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
function Send-Production([string]$Path, $Data) {
 $options = @{ Uri=($Origin + '/api/' + $Path); WebSession=$session; TimeoutSec=90 }
 if ($null -ne $Data) { $options.Method='POST'; $options.ContentType='application/json'; $options.Body=($Data | ConvertTo-Json -Depth 12 -Compress) }
 try { Invoke-RestMethod @options }
 catch { throw ('Production could not complete ' + $Path + '. Keep Production and the Employee Owner service open. ' + $_.Exception.Message) }
}
function Read-Password([string]$Label) {
 $secret = Read-Host $Label -AsSecureString
 $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
 try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
 finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secret.Dispose() }
}
Write-Host 'Connect your existing Backwoods apps'
Write-Host 'Production keeps its original screens. This is one-time background connection setup.'
Write-Host 'Open Production and start the Employee Owner service before continuing.'
$state = Send-Production 'me' $null
if ($state.setup) { throw 'Create your original manager account in Production first, then run this setup again.' }
if (!$state.central) {
 $username = Read-Host 'Current Production manager username'
 $password = Read-Password 'Current Production manager password'
 try { $null = Send-Production 'login' @{username=$username;password=$password} }
 finally { $password=$null }
}
$username = Read-Host 'Employee/Employer username with Production manager access'
$password = Read-Password 'Employee/Employer password'
try {
 if ($state.central) { $null = Send-Production 'login' @{username=$username;password=$password}; $catalog = Send-Production 'integrations/catalog' @{} }
 else { $catalog = Send-Production 'integrations/prepare' @{username=$username;password=$password} }
} finally { $password=$null }
if (!$state.central) {
 $owners = @($catalog.accountingOwners)
 if (!$owners.Count) { throw 'Connect the existing company owner in Business Accounting first.' }
 for ($i=0; $i -lt $owners.Count; $i++) { Write-Host (([string]($i+1)) + '. ' + $owners[$i].name) }
 $choice = 0
 if (![int]::TryParse((Read-Host 'Number of the existing Accounting company owner'), [ref]$choice) -or $choice -lt 1 -or $choice -gt $owners.Count) { throw 'Select one of the listed company owners.' }
 Write-Host 'Reconcile Production opening balances with your existing Accounting books and Vendor stock first.'
 if ((Read-Host 'Type CONNECT after reviewing those balances') -cne 'CONNECT') { throw 'No company connection was made.' }
 $null = Send-Production 'integrations/connect' @{accountingOwnerUid=$owners[$choice-1].uid;reviewed=$true}
}
$records = (Send-Production 'state' $null).records
$skus = @($records | Where-Object { $_.kind -eq 'batches' -and $_.sku -and !$_.bulk } | Select-Object -ExpandProperty sku -Unique)
foreach ($sku in $skus) {
 $batches = @($records | Where-Object { $_.kind -eq 'batches' -and $_.sku -eq $sku -and !$_.bulk -and $_.packages -gt 0 })
 $weights = @($batches | ForEach-Object { [math]::Round(([double]$_.output / [double]$_.packages), 8) } | Select-Object -Unique)
 if ($weights.Count -ne 1) { Write-Warning "SKU $sku has different package sizes; give each package size its own exact SKU before mapping."; continue }
 $products = @($catalog.products | Where-Object { $_.sku -ceq $sku -and $_.unit -in @('each','bag') })
 if ($products.Count -ne 1) { Write-Warning "Create one exact Vendor SKU $sku stocked by each or bag, then rerun this setup."; continue }
 Write-Host ("Production SKU $sku -> " + $products[0].name + ' (' + $weights[0] + ' lb/package).')
 if ((Read-Host 'Type MAP after confirming these packages are not already counted in Vendor; Enter skips') -ceq 'MAP') {
  $null = Send-Production 'integrations/map' @{sku=$sku;productId=$products[0].id;weightLb=$weights[0];reviewed=$true}
 }
}
$result = Send-Production 'integrations/sync' @{}
Write-Host $result.message
Write-Host 'Close and reopen Production, then sign in there with your Employee/Employer username and password.'
Write-Host 'Continue using the same Production screens. Employee/Employer manages access; Accounting shows import status.'
