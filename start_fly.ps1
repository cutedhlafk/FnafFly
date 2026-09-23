$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
# Run independently of this launcher/console. Keep diagnostics on disk.
$existingTrainer = $false
try {
    $state = Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -TimeoutSec 2
    if ($state.application -eq 'fly-ucn-autotrainer') {
        $existingTrainer = $true
        $page = Invoke-WebRequest 'http://127.0.0.1:8766/' -TimeoutSec 3
        $token = [regex]::Match($page.Content, 'name="fly-token" content="([^"]+)"').Groups[1].Value
        if (-not $token) { throw 'Brak tokenu sterowania lokalnym trenerem.' }
        Invoke-RestMethod 'http://127.0.0.1:8766/api/command' -Method Post -ContentType 'application/json' -Headers @{'X-Fly-Token'=$token;Origin='http://127.0.0.1:8766'} -Body '{"command":"start"}' -TimeoutSec 3 | Out-Null
        Start-Process 'http://127.0.0.1:8766/'
        exit 0
    }
} catch { if ($existingTrainer) { throw } }
$python = Join-Path $root '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
if (-not (Test-Path -LiteralPath $python)) { throw 'Brak .venv\Scripts\python.exe. Zobacz README.md.' }
$trainerProcess = Start-Process -FilePath $python -ArgumentList 'src\autotrainer.py','--no-browser' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'logs\auto_stdout.log') -RedirectStandardError (Join-Path $root 'logs\auto_stderr.log') -PassThru
$startupDeadline = (Get-Date).AddSeconds(40)
while ((Get-Date) -lt $startupDeadline) {
    try {
        $state = Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -TimeoutSec 2
        if ($state.application -eq 'fly-ucn-autotrainer') {
            Start-Process 'http://127.0.0.1:8766/'
            Write-Host 'Trener gotowy. F7 wznawia, F12 zatrzymuje.'
            exit 0
        }
    } catch { }
    if ($trainerProcess.HasExited) { break }
    Start-Sleep -Milliseconds 300
}
Get-Content -LiteralPath (Join-Path $root 'logs\auto_stderr.log') -Tail 15 -ErrorAction SilentlyContinue
throw 'Trener nie uruchomil panelu. Sprawdz logs\auto_stderr.log i logs\autotrainer.log.'
