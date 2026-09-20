param([switch]$Quiet)
$ErrorActionPreference = 'Stop'
$ruleName = 'FlyUCN-Viewer-8766'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Nie znaleziono lokalnego Pythona.' }
$runtimePath = (& $pythonPath -c 'import sys; print(sys._base_executable)').Trim()
if (-not (Test-Path -LiteralPath $runtimePath)) { throw 'Nie znaleziono interpretera uruchamianego przez venv.' }
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Fly UCN - podglad telefonu' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766 -RemoteAddress LocalSubnet -Program $runtimePath -Profile Private,Public | Out-Null
} else {
    Set-NetFirewallRule -Name $ruleName -Program $runtimePath -RemoteAddress LocalSubnet -Protocol TCP -LocalPort 8766 -Profile Private,Public -Enabled True | Out-Null
}
Write-Host 'Podglad udostepniony tylko w lokalnej podsieci na porcie 8766.'
if (-not $Quiet) { Read-Host 'Enter, aby zamknac' }
