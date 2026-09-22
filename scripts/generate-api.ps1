$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

Push-Location (Join-Path $repoRoot 'backend')
uv run python ..\scripts\export_openapi.py
Pop-Location

Push-Location (Join-Path $repoRoot 'frontend')
npm run api:generate
Pop-Location
