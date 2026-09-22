[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$ApiPort = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()

$previousApiPort = $env:MINDMATE_API_PORT
$env:MINDMATE_API_PORT = "$ApiPort"
$backend = Start-Process -FilePath 'uv' -ArgumentList @('run', 'uvicorn', 'mindmate.main:app', '--host', '127.0.0.1', '--port', "$ApiPort", '--reload') -WorkingDirectory (Join-Path $repoRoot 'backend') -PassThru -WindowStyle Hidden
try {
    Push-Location (Join-Path $repoRoot 'frontend')
    npm run dev -- --host 127.0.0.1 --port $WebPort
}
finally {
    Pop-Location
    if($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
    $env:MINDMATE_API_PORT = $previousApiPort
}
