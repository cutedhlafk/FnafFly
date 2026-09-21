$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
# Run independently of this launcher/console. Keep diagnostics on disk.
try {
    $state = Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -TimeoutSec 2
    if ($state.application -eq 'fly-ucn-autotrainer') {
        Start-Process 'http://127.0.0.1:8766/'
        exit 0
    }
} catch { }
$python = Join-Path $root '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
Start-Process -FilePath $python -ArgumentList 'src\autotrainer.py' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'logs\auto_stdout.log') -RedirectStandardError (Join-Path $root 'logs\auto_stderr.log')
