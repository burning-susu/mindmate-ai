[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

$backend = Start-Process -FilePath 'uv' -ArgumentList @('run', 'uvicorn', 'mindmate.main:app', '--host', '127.0.0.1', '--port', "$ApiPort", '--reload') -WorkingDirectory (Join-Path $repoRoot 'backend') -PassThru
try {
    Push-Location (Join-Path $repoRoot 'frontend')
    npm run dev -- --host 127.0.0.1 --port $WebPort
}
finally {
    Pop-Location
    if($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}
