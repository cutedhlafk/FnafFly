$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
dotnet build "$PSScriptRoot\audio_capture\AudioCapture.csproj" -c Release -o "$PSScriptRoot\audio_capture\bin\publish" --nologo
if ($LASTEXITCODE -ne 0) { throw 'Nie udało się zbudować pomocnika audio.' }
