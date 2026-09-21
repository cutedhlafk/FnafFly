param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$ruleName = 'FlyUCN-Viewer-8766'

Write-Host ''
Write-Host 'Konfiguruje Zapora Windows dla podgladu FnafFly...'
Write-Host ''

$existing = Get-NetFirewallRule `
    -Name $ruleName `
    -ErrorAction SilentlyContinue

if ($existing) {
    $existing | Remove-NetFirewallRule
}

New-NetFirewallRule `
    -Name $ruleName `
    -DisplayName 'Fly UCN - podglad telefonu' `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8766 `
    -RemoteAddress LocalSubnet `
    -Profile Any | Out-Null

Write-Host 'OK.'
Write-Host ''
Write-Host 'Port TCP 8766 jest dostepny tylko z lokalnej podsieci.'
Write-Host 'Uruchom START_FLY.bat i otworz link z PHONE_LINK.txt.'
Write-Host ''

if (-not $Quiet) {
    Read-Host 'Enter, aby zamknac'
}